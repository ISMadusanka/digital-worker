"""
Google Document AI OCR service.

Sends screenshot images to Document AI for text extraction with
bounding-box layout information.
"""

from google.cloud import documentai
from google.api_core.client_options import ClientOptions

from config import settings
from utils.logger import get_logger

log = get_logger(__name__)


class GoogleOCRService:
    """Thin wrapper around the Document AI ProcessDocument API."""

    def __init__(self) -> None:
        # Document AI endpoint is location-specific
        api_endpoint = f"{settings.GOOGLE_CLOUD_LOCATION}-documentai.googleapis.com"
        opts = ClientOptions(api_endpoint=api_endpoint)

        self._client = documentai.DocumentProcessorServiceClient(
            client_options=opts,
        )

        self._processor_name = self._client.processor_path(
            settings.GOOGLE_CLOUD_PROJECT_ID,
            settings.GOOGLE_CLOUD_LOCATION,
            settings.GOOGLE_DOCUMENT_AI_PROCESSOR_ID,
        )
        log.info("Document AI client ready - processor: %s", self._processor_name)

    def process_image(self, image_bytes: bytes) -> documentai.Document:
        """Send a PNG screenshot to Document AI and return the parsed
        ``Document`` proto.

        Args:
            image_bytes: Raw PNG bytes of the screenshot.

        Returns:
            A ``documentai.Document`` containing extracted text, pages,
            blocks, paragraphs, tokens, and their bounding boxes.
        """
        raw_document = documentai.RawDocument(
            content=image_bytes,
            mime_type="image/png",
        )

        request = documentai.ProcessRequest(
            name=self._processor_name,
            raw_document=raw_document,
        )

        log.info("Sending screenshot to Document AI for OCR …")
        result = self._client.process_document(request=request)
        document = result.document

        log.info(
            "OCR complete — extracted %d characters across %d page(s)",
            len(document.text),
            len(document.pages),
        )
        return document
