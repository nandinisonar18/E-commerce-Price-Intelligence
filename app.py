import logging
from pathlib import Path

from flask import Flask, jsonify, render_template, request

from config import Config
from models import CrawlRun, Offer, Product, db
from services.aggregator import run_search

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Belt-and-braces: if DATABASE_URL was overridden to a sqlite file in a
    # directory that doesn't exist yet, create it before SQLAlchemy tries
    # to open a connection (this is what throws "unable to open database
    # file" otherwise).
    db_uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
    if db_uri.startswith("sqlite:///") and db_uri not in ("sqlite:///:memory:",):
        db_path = Path(db_uri.replace("sqlite:///", "", 1))
        if not db_path.is_absolute():
            db_path = Path.cwd() / db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    with app.app_context():
        db.create_all()

    # Flask's own app.config is a plain dict and only supports dict-style
    # access; the scraper/aggregator layer wants attribute-style access
    # (config.MAX_RETRIES) so it can be unit-tested independently of Flask.
    # We keep the original settings object (config_class) around for that.
    app.settings = config_class

    register_routes(app)
    return app


def register_routes(app):

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/health")
    def health():
        return jsonify({"status": "ok"})

    @app.route("/api/search", methods=["POST"])
    def api_search():
        payload = request.get_json(silent=True) or request.form
        query = (payload.get("query") or "").strip()
        if not query:
            return jsonify({"error": "query is required"}), 400

        storage = payload.get("storage") or None
        colour = payload.get("colour") or None
        if storage and storage.strip().lower() in ("any", "all"):
            storage = None
        if colour and colour.strip().lower() in ("any", "all", "selected"):
            colour = None
        budget_min = _to_float(payload.get("budget_min"))
        budget_max = _to_float(payload.get("budget_max"))
        down_payment = _to_float(payload.get("down_payment")) or 0.0
        tenure_months = int(payload.get("tenure_months") or app.settings.DEFAULT_TENURE_MONTHS)
        interest_rate = _to_float(payload.get("interest_rate")) or app.settings.DEFAULT_INTEREST_RATE_ANNUAL
        sources = payload.get("sources")
        if isinstance(sources, str):
            sources = [s.strip() for s in sources.split(",") if s.strip()]

        result = run_search(
            app.settings,
            query=query,
            storage=storage,
            colour=colour,
            budget_min=budget_min,
            budget_max=budget_max,
            down_payment=down_payment,
            tenure_months=tenure_months,
            interest_rate=interest_rate,
            sources=sources,
        )
        return jsonify(result)

    @app.route("/api/product/<product_id>")
    def api_product(product_id):
        product = Product.query.get_or_404(product_id)
        return jsonify(product.to_dict())

    @app.route("/api/offers/<product_id>")
    def api_offers(product_id):
        offers = Offer.query.filter_by(product_id=product_id).order_by(Offer.scraped_at.desc()).all()
        return jsonify([o.to_dict() for o in offers])

    @app.route("/api/price-history/<product_id>")
    def api_price_history(product_id):
        offers = (
            Offer.query.filter_by(product_id=product_id)
            .order_by(Offer.scraped_at.asc())
            .all()
        )
        history = [
            {
                "source": o.source,
                "effective_price": o.effective_price,
                "scraped_at": o.scraped_at.isoformat() if o.scraped_at else None,
            }
            for o in offers
        ]
        return jsonify(history)

    @app.route("/api/crawl/<crawl_id>")
    def api_crawl(crawl_id):
        crawl = CrawlRun.query.get_or_404(crawl_id)
        return jsonify({
            "id": crawl.id,
            "query": crawl.query,
            "started_at": crawl.started_at.isoformat() if crawl.started_at else None,
            "finished_at": crawl.finished_at.isoformat() if crawl.finished_at else None,
            "sources_requested": crawl.sources_requested,
            "sources_succeeded": crawl.sources_succeeded,
            "sources_failed": crawl.sources_failed,
        })

    @app.errorhandler(404)
    def not_found(_e):
        return jsonify({"error": "not found"}), 404

    @app.errorhandler(500)
    def server_error(e):
        app.logger.exception("Unhandled server error")
        return jsonify({"error": "internal server error"}), 500


def _to_float(value):
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


app = create_app()

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
