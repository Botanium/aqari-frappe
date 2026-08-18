# Aqari Frappe app

This is the synthetic-only Aqari Frappe v16 application. It models office
scope, office applications, parties, properties, transactions, reviews,
withdrawals, and append-only audit events.

Install it in a Frappe v16 bench as `aqari`, then run:

```text
bench --site <site> migrate
bench --site <site> execute aqari.setup.seed.seed_demo
```

The named portal methods are available under `/api/method/aqari.api.*`:

- `health`, `session`, `dashboard`
- `list_transactions`, `transaction_detail`
- `create_transaction`, `update_transaction`, `submit_transaction`
- `review_transaction`, `withdrawal`
- `create_office_application`, `update_office_application`,
  `submit_office_application`, `review_office_application`, and
  `approve_or_return_office_application`

There is no arbitrary resource or method proxy. Preview data and all seed
identities are synthetic; Iraqi legal/authority, biometric, payment, and
production acceptance are intentionally not claimed.
