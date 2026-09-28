import uuid
from datetime import datetime

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def gen_uuid():
    return str(uuid.uuid4())


class CrawlRun(db.Model):
    """One search request = one crawl run, so results can be traced back
    to exactly which sources succeeded/failed and when."""

    __tablename__ = "crawl_runs"

    id = db.Column(db.String(36), primary_key=True, default=gen_uuid)
    query = db.Column(db.String(255), nullable=False)
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    finished_at = db.Column(db.DateTime)
    sources_requested = db.Column(db.String(255))
    sources_succeeded = db.Column(db.String(255))
    sources_failed = db.Column(db.String(255))
    notes = db.Column(db.Text)

    offers = db.relationship("Offer", backref="crawl_run", lazy=True)


class Product(db.Model):
    """A normalized, matched product/variant. Multiple Offer rows (one per
    source) can point at the same Product once matching has run."""

    __tablename__ = "products"

    id = db.Column(db.String(36), primary_key=True, default=gen_uuid)
    variant_id = db.Column(db.String(255), index=True, nullable=False)  # stable match key
    brand = db.Column(db.String(100))
    model = db.Column(db.String(255))
    storage = db.Column(db.String(50))
    colour = db.Column(db.String(50))
    canonical_name = db.Column(db.String(255))
    image_url = db.Column(db.String(1024))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    offers = db.relationship("Offer", backref="product", lazy=True)

    def to_dict(self):
        return {
            "id": self.id,
            "variant_id": self.variant_id,
            "brand": self.brand,
            "model": self.model,
            "storage": self.storage,
            "colour": self.colour,
            "canonical_name": self.canonical_name,
            "image_url": self.image_url,
        }


class Offer(db.Model):
    """A single source's price/offer snapshot for a product at a point in
    time. Rows are append-only, so this table doubles as price history."""

    __tablename__ = "offers"

    id = db.Column(db.String(36), primary_key=True, default=gen_uuid)
    product_id = db.Column(db.String(36), db.ForeignKey("products.id"), nullable=False)
    crawl_run_id = db.Column(db.String(36), db.ForeignKey("crawl_runs.id"))

    source = db.Column(db.String(100), nullable=False)
    product_url = db.Column(db.String(1024))
    product_name = db.Column(db.String(255))
    sku = db.Column(db.String(255))

    currency = db.Column(db.String(10), default="INR")
    mrp = db.Column(db.Float)
    selling_price = db.Column(db.Float)
    discount = db.Column(db.Float)
    availability = db.Column(db.String(50))
    seller = db.Column(db.String(255))
    rating = db.Column(db.Float)
    review_count = db.Column(db.Integer)

    offer_text = db.Column(db.Text)
    offer_type = db.Column(db.String(100))
    bank = db.Column(db.String(100))
    offer_discount = db.Column(db.Float)

    emi_available = db.Column(db.Boolean, default=False)
    emi_tenure = db.Column(db.Integer)
    emi_rate = db.Column(db.Float)
    emi_monthly = db.Column(db.Float)

    effective_price = db.Column(db.Float)
    deal_score = db.Column(db.Float)

    is_fixture_fallback = db.Column(db.Boolean, default=False)
    scraped_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "product_id": self.product_id,
            "source": self.source,
            "product_url": self.product_url,
            "product_name": self.product_name,
            "sku": self.sku,
            "currency": self.currency,
            "mrp": self.mrp,
            "selling_price": self.selling_price,
            "discount": self.discount,
            "availability": self.availability,
            "seller": self.seller,
            "rating": self.rating,
            "review_count": self.review_count,
            "offer_text": self.offer_text,
            "offer_type": self.offer_type,
            "bank": self.bank,
            "offer_discount": self.offer_discount,
            "emi_available": self.emi_available,
            "emi_tenure": self.emi_tenure,
            "emi_rate": self.emi_rate,
            "emi_monthly": self.emi_monthly,
            "effective_price": self.effective_price,
            "deal_score": self.deal_score,
            "is_fixture_fallback": self.is_fixture_fallback,
            "scraped_at": self.scraped_at.isoformat() if self.scraped_at else None,
        }
