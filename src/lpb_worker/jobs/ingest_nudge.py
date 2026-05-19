"""Monthly cron job: nudge admins that the new price book should be available.

NJ ABC requires wholesalers to file the Current Price List by the 15th, locking
prices for the following month. We run this on the 16th to remind admins to
upload the fresh PDF.
"""

import logging
import sys

from lpb_core.settings import settings

log = logging.getLogger("lpb_cron_ingest_nudge")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s")


def main() -> int:
    log.info("ingest-nudge cron firing (env=%s)", settings.app_env)
    # Real implementation in week 11-12: query for tenants with admin role,
    # send a Resend email reminding them to upload the new book.
    return 0


if __name__ == "__main__":
    sys.exit(main())
