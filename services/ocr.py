"""
OmniParser OCR service.

Sends screenshot images to a local OmniParser API for UI element detection
with bounding-box layout and interactivity information.
"""

import io
import requests

from config import settings
from utils.logger import get_logger

log = get_logger(__name__)


class OmniParserService:
    """Sends screenshots to the OmniParser API and returns parsed UI data."""

    def __init__(self) -> None:
        self._api_url = settings.OMNIPARSER_API_URL
        self._box_threshold = settings.OMNIPARSER_BOX_THRESHOLD
        self._iou_threshold = settings.OMNIPARSER_IOU_THRESHOLD
        self._use_paddleocr = settings.OMNIPARSER_USE_PADDLEOCR
        self._imgsz = settings.OMNIPARSER_IMGSZ

        log.info(
            "OmniParser client ready — endpoint: %s (box=%.2f, iou=%.2f, paddleocr=%s, imgsz=%d)",
            self._api_url,
            self._box_threshold,
            self._iou_threshold,
            self._use_paddleocr,
            self._imgsz,
        )

    def process_image(self, image_bytes: bytes) -> dict:
        """Send a PNG screenshot to OmniParser and return the parsed result.

        Args:
            image_bytes: Raw PNG bytes of the screenshot.

        Returns:
            A dict containing ``parsed_content_list`` (str) and
            ``label_coordinates`` (dict).  The ``image_base64`` field
            is stripped before returning to save memory.
        """
        files = {
            "image": ("screenshot.png", io.BytesIO(image_bytes), "image/png"),
        }

        data = {
            "box_threshold": str(self._box_threshold),
            "iou_threshold": str(self._iou_threshold),
            "use_paddleocr": str(self._use_paddleocr).lower(),
            "imgsz": str(self._imgsz),
        }

        log.info("Sending screenshot to OmniParser for processing …")

        response = requests.post(
            self._api_url,
            files=files,
            data=data,
            timeout=60,
        )
        response.raise_for_status()
        result = response.json()

        # Strip image_base64 — not needed downstream and can be very large
        result.pop("image_base64", None)

        # Count detected elements for logging
        content_list = result.get("parsed_content_list", "")
        num_elements = content_list.count("\nicon ") + (1 if content_list.startswith("icon ") else 0)

        log.info("OmniParser complete — detected %d UI elements", num_elements)
        return result
