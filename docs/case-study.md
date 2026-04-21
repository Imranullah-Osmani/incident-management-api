# Backend Repair Case Study

## Original problem

Ticket creation worked in the API, but async notification delivery was unreliable in the containerized environment. In the failure mode that mattered most, the application tried to enqueue a Celery task even when the broker path was not truly ready. That created two bad outcomes:

- requests could fail when the broker connection path was unavailable
- notifications could appear "accepted" while the worker side was not correctly wired to consume the task

## Investigation

The repair work focused on isolating where the failure actually lived instead of assuming the API, worker, and broker were all healthy together.

1. Verified the synchronous API path first by creating tickets without relying on the queue.
2. Checked readiness behavior separately for database and Redis so degraded states were visible.
3. Confirmed the worker process was connected to the broker profile and inspected task registration.
4. Reproduced the failure with a minimal flow: login, create ticket, inspect worker logs, inspect readiness output.

The important finding was that the async path needed two explicit protections:

- broker availability needed to be checked before enqueueing work
- Celery needed an explicit import path for the notification task so the worker could always register it

## What changed

The repair introduced a small but meaningful set of changes:

1. Added a broker reachability check before dispatching notification tasks.
2. Switched the API into a clear degraded mode when Redis was unavailable instead of failing blindly.
3. Registered the notification task explicitly in Celery configuration.
4. Updated startup behavior so demo users and auth data stayed consistent across rebuilds.
5. Tightened the readiness signal so browser and ops checks reflected whether the system was running in degraded or brokered mode.

## Result

After the change:

- ticket creation remained available even when the async broker was missing
- readiness output clearly reported degraded versus brokered mode
- Celery workers consumed notification tasks successfully once Redis and the worker profile were online
- the system behavior was easier to reason about during local Docker demos and interview walkthroughs

## Recreated sample

The recreated sample in [recreated_sample](../recreated_sample/README.md) strips the repair down to the essential pattern:

- a "before" flow that publishes work without checking the broker path
- an "after" flow that detects degraded conditions and uses an explicit task registry
- a small test file that demonstrates the difference in behavior
