from django.core.management.base import BaseCommand
from payouts.models import Merchant, BankAccount, Transaction


class Command(BaseCommand):
    help = "Seed merchants with credit history"

    def handle(self, *args, **options):
        merchants_data = [
            {
                "name": "Acme Design Studio",
                "email": "acme@example.com",
                "credits": [500000, 250000, 100000],  # 8500 INR total
            },
            {
                "name": "Pixel Labs",
                "email": "pixel@example.com",
                "credits": [1000000, 500000],  # 15000 INR total
            },
            {
                "name": "WebForge Co",
                "email": "webforge@example.com",
                "credits": [750000, 300000, 200000],  # 12500 INR total
            },
        ]

        for data in merchants_data:
            merchant, created = Merchant.objects.get_or_create(
                email=data["email"],
                defaults={"name": data["name"]},
            )
            BankAccount.objects.get_or_create(
                merchant=merchant,
                defaults={
                    "account_number": "1234567890",
                    "ifsc_code": "HDFC0001234",
                    "account_holder_name": data["name"],
                },
            )
            for amount in data["credits"]:
                Transaction.objects.create(
                    merchant=merchant,
                    txn_type=Transaction.CREDIT,
                    amount_paise=amount,
                    description="Simulated customer payment",
                )
            status = "Created" if created else "Already exists"
            self.stdout.write(
                self.style.SUCCESS(f"{status}: {merchant.name}")
            )

        self.stdout.write(
            self.style.SUCCESS("Seeding completed successfully!")
        )
