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

On October 17, manual dispatch returned HTTP 422, `Actions has been disabled
for this repository`, even though the repository Actions permissions endpoint
reported `enabled=true` and the workflow reported `state=active`. The signed-in
Actions page explained that GitHub had automatically disabled workflows on this
fork to reduce wasted compute. Re-enable through its explicit confirmation
button; the page confirmed `Actions Enabled` and accepted probe run #90.

Verification on October 17: main's 21 focused tests passed; after merging the
same fix into the Mac development branch, its 30 affected tests passed. Live
[probe #90](https://github.com/AlexbeatsZ/Fudan_iCourse_Subscriber/actions/runs/38997702926)
completed successfully in 2m55s, authenticated to iCourse, loaded the encrypted
cloud database, checked all seven courses and reported `needed=true`. The ASR
job was skipped intentionally because `probe_only=true`.

[Normal run #91](https://github.com/AlexbeatsZ/Fudan_iCourse_Subscriber/actions/runs/38997984175)
was then dispatched to resume pending processing. Its discovery, processing and
encrypted database deployment jobs completed successfully. The following
[normal run #92](https://github.com/AlexbeatsZ/Fudan_iCourse_Subscriber/actions/runs/39141217962)
also completed all three stages successfully.

## Recovering a stalled schedule

On October 21 (America/New_York), the workflow was `active` and a fresh
[read-only probe #93](https://github.com/AlexbeatsZ/Fudan_iCourse_Subscriber/actions/runs/39716340304)
successfully logged in, loaded the encrypted database and checked all seven
courses. However, the last recorded `schedule` event was October 14 at
19:58 UTC; subsequent successful runs were manual dispatches. Manual success
therefore does not verify automatic scheduling.

GitHub documents changing the cron expression as a recovery action when a
scheduled workflow stops despite remaining enabled. Re-register the existing
times with `0 4-22/6 * * *`, equivalent to `0 4,10,16,22 * * *`: 04:00,
10:00, 16:00 and 22:00 UTC (12:00, 18:00, 24:00 and 06:00 Beijing time).
This is a recovery attempt; the provider's internal reason for the scheduling
gap is unknown, and an actual subsequent `schedule` run is required to confirm
recovery. See [GitHub's workflow troubleshooting guide](https://docs.github.com/en/actions/how-tos/troubleshoot-workflows#scheduled-workflow-stopped-running).
