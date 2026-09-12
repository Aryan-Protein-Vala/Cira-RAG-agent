"""Create a superadmin and a partner admin for local testing.

Superseded by seed_admins.py, which takes the same values from the environment.
This wrapper stays because some setup notes call it by name. Credentials are
NEVER hard-coded: run it with the variables below set.

    CIRA_SUPERADMIN_EMAIL / CIRA_SUPERADMIN_PASSWORD
    CIRA_PARTNER_EMAIL     / CIRA_PARTNER_PASSWORD
"""

import asyncio

from seed_admins import seed

if __name__ == "__main__":
    asyncio.run(seed())
