import logging

from odoo import models

_logger = logging.getLogger(__name__)


class MailMessage(models.Model):
    _inherit = "mail.message"

    def process_generation_urls(self, urls):
        """Process URLs and create attachments, return markdown content.

        Args:
            urls: List of URL data from model.generate()

        Returns:
            tuple: (markdown_content, attachments)
        """
        self.ensure_one()
        attachments = []
        markdown_parts = []

        for i, url_data in enumerate(urls):
            # Create attachment linked to this message
            attachment = self._create_url_attachment(url_data)
            if attachment:
                attachments.append(attachment)

            # Generate markdown
            content_type = url_data.get("content_type", "")
            url = url_data["url"]

            if content_type.startswith("image/"):
                markdown_parts.append(f"![Generated Image {i+1}]({url})")
            elif content_type.startswith("video/"):
                markdown_parts.append(f"[Generated Video {i+1}]({url})")
            elif content_type.startswith("audio/"):
                markdown_parts.append(f"[Generated Audio {i+1}]({url})")
            else:
                markdown_parts.append(f"[Generated Content {i+1}]({url})")

        # Update this message's attachment_ids
        if attachments:
            attachment_ids = [(4, att.id) for att in attachments]
            self.write({"attachment_ids": attachment_ids})

        return "\n\n".join(markdown_parts), attachments

    def _create_url_attachment(self, url_data):
        """Create attachment record for URL linked to this message"""
        return self.env["ir.attachment"].create(
            {
                "name": url_data.get("filename", "generated_content"),
                "type": "url",
                "url": url_data["url"],
                "mimetype": url_data.get("content_type", "application/octet-stream"),
                "res_model": "mail.message",
                "res_id": self.id,
            }
        )
