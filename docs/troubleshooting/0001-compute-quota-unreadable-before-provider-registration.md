# 0001. Compute quota is unreadable before provider registration

Date: 2026-10-10

## Symptom

On a subscription that had never deployed compute:

1. `az vm list-usage -l swedencentral -o json` returned an empty list and exit code 0.
2. The Quota API returned an error:

   ```text
   MissingRegistrationForResourceProvider: The subscription is not in registered state
   for the resource provider: Microsoft.Quota.
   ```

3. The SKU listing worked, and reported no subscription restrictions in West US 2:

   ```bash
   az rest --method get \
     --url "https://management.azure.com/subscriptions/<subscription-id>/providers/Microsoft.Compute/skus?api-version=2021-07-01&\$filter=location eq 'westus2'"
   ```

   0 of 1344 VM sizes carried a `NotAvailableForSubscription` restriction.

An empty quota list with a success exit code reads like "no limits apply". It means "no data".

## Cause

**Confirmed:** the `Microsoft.Compute` resource provider was not registered. The usage endpoint returns an empty list for an unregistered provider instead of an error.

```bash
az provider list --query "[?namespace=='Microsoft.Compute'].registrationState" -o tsv
# NotRegistered
```

**Hypothesis:** SKU restriction data is incomplete before registration. After registration, West US 2 reported 412 of 1344 sizes restricted. Sweden Central, West Europe, and Norway East reported the same counts before and after. No documentation was found that explains the difference, so the mechanism is unconfirmed.

## Fix

Register the provider and wait for completion. Registration creates no resources and has no charge.

```bash
az provider register -n Microsoft.Compute --wait
```

## Verification

```bash
az provider show -n Microsoft.Compute --query registrationState -o tsv
# Registered

az vm list-usage -l swedencentral --query "[?name.value=='cores']" -o table
# CurrentValue    Limit    Unit    LocalName
# --------------  -------  ------  --------------------
# 0               4        Count   Total Regional vCPUs
```

The usage call returned 232 rows for Sweden Central after registration.

## Lessons

- Treat an empty quota response as missing data. Check provider registration first.
- Do not base a region choice on SKU restrictions read before `Microsoft.Compute` is registered.
- The same pattern is likely for network quotas and `Microsoft.Network`. That call returned `SubscriptionHasNoUsages` before registration and has not been re-tested.
