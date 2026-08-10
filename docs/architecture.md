# Architecture

The platform separates request handling from potentially slower analytical work.

1. The API fetches weekly observations from Open Data NY and stores a normalized snapshot
   in Redis.
2. Read endpoints query observations by region and date range.
3. Analysis requests are persisted as jobs and appended to a Redis queue.
4. A separate worker claims a job, computes descriptive statistics and a least-squares
   trend, then persists either a result or a bounded error message.

Redis is deliberately used for both the dataset snapshot and job coordination so the API
and worker remain stateless. Kubernetes can therefore scale the API independently from the
worker. A single worker replica is the conservative default. `BRPOP` removes a job ID when
it is claimed, so the compact demonstration queue is at-most-once after dequeue; it does not
implement leases, acknowledgement, retries, or dead-letter handling.

## Reliability boundaries

- Refresh replaces the dataset in one Redis transaction after the complete upstream
  response has been parsed successfully.
- A claimed job transitions from `submitted` to `running`, then to `complete` or `failed`.
- A worker process that terminates after removing a queued job can leave it in `submitted`
  or `running` with no automatic retry. A production extension would use a processing queue,
  acknowledgements, expiring leases, retry limits, and dead-letter handling.
- Redis uses ephemeral storage in the supplied Kubernetes base. Persistent storage and
  backups are deployment-specific concerns and are not implied here.
- The public API is intentionally unauthenticated for demonstration. Production deployment
  should place refresh and job-creation routes behind authentication and rate limiting.

## Analytical definition

For a selected region and interval, the worker reports count, mean, population standard
deviation, minimum, and maximum. It also fits

`price = intercept + slope * weeks_since_first_observation`

with ordinary least squares and reports slope in dollars per gallon per week plus the
coefficient of determination, R-squared. The trend is descriptive, not a forecast or a
causal economic model.
