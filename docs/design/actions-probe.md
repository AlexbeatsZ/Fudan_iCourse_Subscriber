# Actions replay probe

The scheduled `discover` job checks the encrypted data branch and subscribed
recordings before loading ASR/OCR models. A successful probe publishes
`needed=true` or `needed=false`; a failed probe must publish neither.

The job passes its repository `GITHUB_TOKEN` to `cloud_database`. The bearer
header is attached only to the `api.github.com` commit lookup, never to the
archive download or university requests. Local public-repository callers may
continue without a token.

Retry the entire probe at most three times, with 5/10 second delays, for
timeouts, connection failures, non-JSON responses, HTTP 408/429/5xx transient
statuses, or HTTP 403 explicitly marked as rate limited. Close the school
session after every attempt. Authentication/permission errors and persistent
failures remain failures. Only a 404 from the data-branch commit endpoint
counts as first run; an archive 404 must fail.

Log the operation before each remote phase. Error summaries include exception
type, HTTP status and host; never print response bodies, bearer headers,
signed URLs, query strings or CAS tickets.

Manual dispatch normally forces processing as before. Set boolean
`probe_only=true` to validate real login, encrypted database loading and course
enumeration without forcing ASR. Scheduled behavior is unchanged.

The September 16 run #2 lost its job logs, so its exact historical cause is
unknown. Runs #23 and #80 failed after successful login with only `HTTPError`
logged. Anonymous GitHub access and lack of retries are confirmed code gaps;
the old logs do not identify their exact HTTP status or failing service.
