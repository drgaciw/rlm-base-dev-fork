// without sharing (issue X7; comment corrected by A-C7, docs/ARCHITECT_REVIEW.md
// WP-11): no flow or other metadata invokes this class — a repo-wide search finds
// no CreateAssetOrderEvent-triggered flow calling it, only classAccesses grants in
// the Admin profile and the partner-facing `RLM Custom Partner Community User`
// profile / `RLM_Partner_Community_User_Perm_Set`. As an @InvocableMethod it is
// therefore reachable directly via the REST Invocable Actions API by any user
// holding one of those grants, including partner community users, not only by an
// internal automated-process context.
//
// DECISION: kept `without sharing`. Asset renewal bookkeeping must recalculate
// consistently regardless of the calling user's record-level sharing, and the
// method only ever writes RenewalTerm/RenewalTermUnit/PricingSource on Assets
// whose Ids the caller already supplied — it does not expose a broader read/write
// surface. CRUD is checked (isCreateable/isUpdateable) before the upsert, but
// there is no FLS check and no ownership/ACL validation that the caller-supplied
// AssetIds belong to them; a partner user with the invocable grant can overwrite
// renewal fields on any Asset Id they can guess or discover elsewhere. Tightening
// that (e.g. moving to `with sharing` + USER_MODE, or restricting the action's
// availability to internal profiles only) is out of scope for this pass — it needs
// a live-org check of the actual partner community flows before behavior changes
// (see docs/ARCHITECT_REVIEW.md §6.A I6 org-validation block).
public without sharing class RLM_AssetInfoUtility{
    @InvocableMethod(label='Calculate Asset Info', description='Returns Asset Renewal Info')
    public static void calculateAssetRenewInfo(List<CreateAssetOrderEvent> assetOrderCreationEvents){
        if (assetOrderCreationEvents.isEmpty()){
            return;
        }

        CreateAssetOrderEvent assetOrderCreationEvent = assetOrderCreationEvents.get(0);
        Map<Id, OrderItem> orderItemsMap = fetchOrderItems(assetOrderCreationEvent.AssetDetails);
        Map<Id, AssetContractRelationship> acrMap = fetchAssetContractRelationships(assetOrderCreationEvent.AssetDetails);

        List<Asset> assetsToUpdate = new List<Asset>();

        for (CreateAssetOrderDtlEvent assetDetailEvent : assetOrderCreationEvent.AssetDetails){
            assetsToUpdate.add(processAssetDetailEvent(assetDetailEvent, orderItemsMap, acrMap));
        }

        if (!assetsToUpdate.isEmpty()){
            // Check CRUD permissions before upsert operation
            if (Schema.sObjectType.Asset.isCreateable() && Schema.sObjectType.Asset.isUpdateable()){
                upsert assetsToUpdate;
            }
        }
    }

    private static Map<Id, OrderItem> fetchOrderItems(List<CreateAssetOrderDtlEvent> assetDetailEvents){
        Set<Id> orderItemIds = new Set<Id>();
        for (CreateAssetOrderDtlEvent event : assetDetailEvents){
            orderItemIds.add(event.OrderItemId);
        }

        return new Map<Id, OrderItem>([SELECT Id, ServiceDate, EndDate, OrderAction.Type, ProductSellingModel.SellingModelType, ProductSellingModel.PricingTermUnit, Product2.Name
                                       FROM OrderItem
                                       WHERE Id IN:orderItemIds]);
    }

    private static Map<Id, AssetContractRelationship> fetchAssetContractRelationships(List<CreateAssetOrderDtlEvent> assetDetailEvents){
        Set<Id> assetIds = new Set<Id>();
        for (CreateAssetOrderDtlEvent event : assetDetailEvents){
            assetIds.add(event.AssetId);
        }

        return new Map<Id, AssetContractRelationship>([SELECT Id, AssetId, Contract.ContractTerm
                                                       FROM AssetContractRelationship
                                                       WHERE AssetId IN:assetIds]);
    }

    private static Asset processAssetDetailEvent(CreateAssetOrderDtlEvent assetDetailEvent, Map<Id, OrderItem> orderItemsMap, Map<Id, AssetContractRelationship> acrMap){
        OrderItem oi = orderItemsMap.get(assetDetailEvent.OrderItemId);
        Asset assetToUpdate = new Asset();
        assetToUpdate.Id = assetDetailEvent.AssetId;

        if (oi.OrderAction.Type == 'Add'){
            setRenewalInfoForNewAsset(oi, assetToUpdate);
        } else{
            updateRenewalInfoForExistingAsset(acrMap.get(assetDetailEvent.AssetId), assetToUpdate);
        }

        return assetToUpdate;
    }

    private static void setRenewalInfoForNewAsset(OrderItem oi, Asset assetToUpdate){
        if (oi.ProductSellingModel.SellingModelType == 'TermDefined' && oi.ProductSellingModel.PricingTermUnit == 'Months'){
            Integer monthsBetween = oi.ServiceDate.monthsBetween(oi.EndDate) + ((oi.EndDate.day() > oi.ServiceDate.day()) ? 1 : 0);
            assetToUpdate.RenewalTerm = (oi.ProductSellingModel.PricingTermUnit == 'Months') ? monthsBetween : monthsBetween / 12;
            assetToUpdate.RenewalTermUnit = oi.ProductSellingModel.PricingTermUnit;
        } else if (oi.ProductSellingModel.SellingModelType == 'Evergreen'){
            assetToUpdate.RenewalTerm = (oi.ProductSellingModel.PricingTermUnit == 'Months') ? 12 : 1;
            assetToUpdate.RenewalTermUnit = oi.ProductSellingModel.PricingTermUnit;
        } else{
            assetToUpdate.RenewalTerm = 1;
            assetToUpdate.RenewalTermUnit = 'Annual';
        }
        assetToUpdate.PricingSource = 'LastTransaction';
    }

    private static void updateRenewalInfoForExistingAsset(AssetContractRelationship acr, Asset assetToUpdate){
        if (acr != null){
            assetToUpdate.RenewalTermUnit = 'Months';
            assetToUpdate.RenewalTerm = acr.Contract.ContractTerm;
            assetToUpdate.PricingSource = 'PriceBookListPrice';
        }
    }

}