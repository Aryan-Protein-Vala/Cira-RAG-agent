# Data Access & Information Security Policy (v4.0)

Owner: IT Security. Applies to every system that stores company or customer data, including SAP Business One.

## Access control

- SAP Business One access is granted per named user (OUSR) and follows least privilege.
- Access requests are approved by the data owner and reviewed every six months.
- Shared or generic accounts are prohibited, including for reporting tools.
- CIRA queries the ERP with a read-only technical user; no write, update or delete operation is ever executed.

## Data classification

- Confidential: salary data (OHEM.salary), customer pricing, unreleased financial results.
- Internal: order, invoice, inventory and vendor data.
- Public: published product catalogue information.

## Exporting data

- Exports of confidential data to Excel or CSV must stay on managed devices.
- Bulk exports of more than 10,000 records must be logged with a business justification.
- Data may not be uploaded to external AI tools that are not on the approved list.

## Incident response

- Suspected data incidents must be reported to security@company.example within one hour.
- The security team triages within four hours and notifies the DPO for personal-data incidents.
