import logging
from typing import List
import json
import datetime
import os
from .base_step import BaseStep, StepContext, StepResult, Navigator
from services.publisher_kafka import KafkaPublisher
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class StepPipeline:
    """Chạy tuần tự một danh sách step và gom kết quả lại."""

    def __init__(self, steps: List[BaseStep], navigator: Navigator):
        self.steps = steps
        self.navigator = navigator

    async def run(self, ctx: StepContext) -> List[StepResult]:
        results: List[StepResult] = []

        # ── Inject worker metadata vào đầu extracted_data ─────────────────────
        ctx.extracted_data.insert(
            0,
            {
                "_metadata": {
                    "worker_id": os.getenv("PROFILE_PATH", "dev-01"),
                    # "pid": ctx.pid,
                    "target_url": ctx.base_url,
                    "started_at": ctx.started_at,
                    "email_account": ctx.email_account,
                }
            },
        )

        for step in self.steps:
            logger.info(f"[crawler] Bắt đầu crawl: {step.label}")
            result = await step.execute(ctx, self.navigator)
            results.append(result)

            if result.success:
                if result.data is not None:
                    ctx.extracted_data.append({step.label: result.data})
                logger.info(f"[crawler] Kết thúc bước '{step.label}': OK")

            elif step.fallback_step is not None:
                # Step thất bại → thử fallback
                fb = step.fallback_step
                logger.warning(
                    f"[crawler] '{step.label}' thất bại ({result.error}), "
                    f"chuyển sang fallback: {fb.label}"
                )
                fb_result = await fb.execute(ctx, self.navigator)
                results.append(fb_result)

                if fb_result.success and fb_result.data is not None:
                    ctx.extracted_data.append({fb.label: fb_result.data})

                status = "OK" if fb_result.success else f"FAILED ({fb_result.error})"
                logger.info(f"[crawler] Fallback '{fb.label}': {status}")

            if not result.success:
                logger.warning(
                    f"[crawler] Kết thúc bước '{step.label}': FAILED ({result.error})"
                )
                finished_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
                ctx.extracted_data[0]["_metadata"]["finished_at"] = finished_at
                logs_kafka = {
                    "error": f"Lỗi bước '{step.label}': FAILED ({result.error})",
                    "metadata": ctx.extracted_data[0]["_metadata"],
                    "url_user": ctx.base_url,
                    "timestamp": finished_at,
                }
                await KafkaPublisher().publish(logs_kafka, topic="error_step_crawl")

        # ── Cập nhật finished_at vào metadata sau khi tất cả step xong ────────
        finished_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        ctx.extracted_data[0]["_metadata"]["finished_at"] = finished_at

        # await KafkaPublisher().publish(
        #     ctx.extracted_data, topic="crawler_result_entity_new"
        # )

        # with open("crawler_result.json", "w") as f:
        #     json.dump(ctx.extracted_data, f)

        logger.info("[crawler] Hoàn thành pipeline.")
        return results
