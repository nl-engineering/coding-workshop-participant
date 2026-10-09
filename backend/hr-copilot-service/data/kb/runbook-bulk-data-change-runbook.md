# Bulk Data Change Runbook

> Domain: Bulk Transactions
> Audience: HR Operations analysts

**Domain:** Bulk Transactions



## Purpose



Step-by-step procedure for: Bulk Data Change Runbook.



## Steps



1. Confirm the request includes a scope definition (which employees/records) and a named requester.

2. Export the current state of the affected records before applying any change, for rollback.

3. Apply changes in a staging batch of no more than 50 records and validate before running the full batch.

4. Run the full batch and capture the job ID, record count, and timestamp in the change log.

5. Notify the requester and affected managers once the batch completes.



## Escalation



Escalate to the Data Engineering on-call if more than 1% of records fail validation.
