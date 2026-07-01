import logging
from typing import List
import json

from .base_step import BaseStep, StepContext, StepResult, Navigator
from services.publisher_kafka import KafkaPublisher

logger = logging.getLogger(__name__)


class StepPipeline:
    """Chạy tuần tự một danh sách step và gom kết quả lại."""

    def __init__(self, steps: List[BaseStep], navigator: Navigator):
        self.steps = steps
        self.navigator = navigator

    async def run(self, ctx: StepContext) -> List[StepResult]:
        results: List[StepResult] = []

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

            else:
                logger.warning(
                    f"[crawler] Kết thúc bước '{step.label}': FAILED ({result.error})"
                )
        await KafkaPublisher().publish(
            ctx.extracted_data, topic="crawler_result_entity"
        )
        with open("crawler_result.json", "w") as f:
            json.dump(ctx.extracted_data, f)

        logger.info("[crawler] Hoàn thành pipeline.")
        return results
