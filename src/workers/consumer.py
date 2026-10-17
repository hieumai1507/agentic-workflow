"""
Redis Streams Consumer: Async Worker Engine executing LangGraph workflows.
"""
import asyncio
import json
import structlog
import redis.asyncio as aioredis
from src.core.config import settings
from src.graph.builder import build_pii_masking_graph

logger = structlog.get_logger(__name__)

STREAM_NAME = settings.STREAM_NAME
GROUP_NAME = settings.GROUP_NAME
CONSUMER_NAME = f"worker_{settings.WORKER_ID}"
DLQ_STREAM = settings.DLQ_STREAM_NAME

graph_app = build_pii_masking_graph()
semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_TASKS)

async def process_stream_message(redis_client: aioredis.Redis, msg_id: str, raw_payload: dict):
    """Executes a single stream message through the compiled LangGraph pipeline."""
    async with semaphore:
        job_id = raw_payload.get("job_id", "unknown_job")
        logger.info("Executing LangGraph pipeline for job", job_id=job_id, msg_id=msg_id)

        initial_state = {
            "job_id": job_id,
            "email_id": raw_payload.get("email_id", ""),
            "sender": raw_payload.get("sender", ""),
            "subject": raw_payload.get("subject", ""),
            "raw_body": raw_payload.get("body", ""),
            "received_at": raw_payload.get("received_at", ""),
            "content_hash": raw_payload.get("content_hash", ""),
            "retry_count": 0,
            "max_retries": settings.LLM_MAX_RETRIES,
            "validation_errors": [],
            "is_fallback_triggered": False,
            "status": "PROCESSING",
            "error_log": []
        }

        try:
            config = {"configurable": {"thread_id": job_id}}
            final_state = await graph_app.ainvoke(initial_state, config=config)

            if final_state.get("status") == "SUCCESS":
                await redis_client.xack(STREAM_NAME, GROUP_NAME, msg_id)
                logger.info(
                    "Job processed successfully and acknowledged",
                    job_id=job_id,
                    ticket_id=final_state.get("dispatched_ticket_id")
                )
                return final_state
            elif final_state.get("status") == "PENDING_HUMAN_REVIEW":
                await redis_client.xack(STREAM_NAME, GROUP_NAME, msg_id)
                logger.warning(
                    "Job safely quarantined in Human-in-the-Loop review queue",
                    job_id=job_id,
                    vault_id=final_state.get("vault_id")
                )
                return final_state
            else:
                logger.error("Job ended in non-success state, routing to DLQ", job_id=job_id, status=final_state.get("status"))
                await route_to_dlq(redis_client, msg_id, raw_payload, final_state.get("error_log", []))
                await redis_client.xack(STREAM_NAME, GROUP_NAME, msg_id)
                return final_state

        except Exception as exc:
            logger.exception("Unhandled error during graph execution", job_id=job_id, error=str(exc))
            await route_to_dlq(redis_client, msg_id, raw_payload, [str(exc)])
            await redis_client.xack(STREAM_NAME, GROUP_NAME, msg_id)
            return None

async def route_to_dlq(redis_client: aioredis.Redis, msg_id: str, raw_payload: dict, error_log: list):
    """Appends failed messages to the Dead-Letter Queue stream."""
    dlq_entry = {
        "original_message_id": msg_id,
        "payload": json.dumps(raw_payload),
        "errors": json.dumps(error_log)
    }
    await redis_client.xadd(DLQ_STREAM, dlq_entry)
    logger.error("Message safely quarantined in DLQ", msg_id=msg_id, dlq=DLQ_STREAM)

async def run_worker_loop(stop_event: asyncio.Event = None, max_iterations: int = None):
    """Main consumer loop reading from Redis Streams with autoclaim."""
    redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)

    # Initialize consumer group if not present
    try:
        await redis_client.xgroup_create(STREAM_NAME, GROUP_NAME, id="0", mkstream=True)
    except aioredis.ResponseError:
        pass  # Group already exists

    logger.info("Worker consumer loop running", stream=STREAM_NAME, group=GROUP_NAME, consumer=CONSUMER_NAME)

    iteration = 0
    while stop_event is None or not stop_event.is_set():
        if max_iterations and iteration >= max_iterations:
            break
        iteration += 1

        try:
            # 1. Recover stale messages from dead workers
            try:
                claims = await redis_client.xautoclaim(
                    STREAM_NAME, GROUP_NAME, CONSUMER_NAME,
                    min_idle_time=settings.IDLE_TIME_FOR_AUTOCLAIM_MS,
                    start_id="0-0", count=5
                )
                claimed_messages = claims[1] if len(claims) > 1 else []
                for msg_id, data in claimed_messages:
                    if "payload" in data:
                        payload = json.loads(data["payload"])
                        asyncio.create_task(process_stream_message(redis_client, msg_id, payload))
            except Exception as e:
                logger.debug("No stale messages or autoclaim error", error=str(e))

            # 2. Read new pending messages
            streams = await redis_client.xreadgroup(
                GROUP_NAME, CONSUMER_NAME,
                {STREAM_NAME: ">"}, count=10, block=1000
            )

            if streams:
                for _, messages in streams:
                    for msg_id, data in messages:
                        if "payload" in data:
                            payload = json.loads(data["payload"])
                            asyncio.create_task(process_stream_message(redis_client, msg_id, payload))

        except Exception as e:
            logger.error("Error reading from Redis Stream", error=str(e))
            await asyncio.sleep(1)

    await redis_client.close()

if __name__ == "__main__":
    asyncio.run(run_worker_loop())
