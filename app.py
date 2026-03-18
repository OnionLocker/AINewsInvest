"""
app.py - Alpha Vault 涓诲簲鐢�

鍔熻兘锛�
  - 閴存潈锛�/login, /register, /logout
  - 椤甸潰锛�/ (dashboard), /settings, /history
  - API锛�/api/health, /api/search, /api/watchlist, /api/quotes, /api/report,
         /api/report/history, /api/report/generate, /api/accuracy, /api/llm/status
"""
import json
import os
from datetime import datetime, date
from flask import Flask, render_template, redirect, url_for, request, flash, jsonify
from flask_login import (
    LoginManager, login_user, logout_user, login_required, current_user,
)
from config import Config
from models import db, User, Watchlist, DailyReport, RecommendationTrack, AlertRule
from utils.logger import app_logger
from utils.notifier import test_notify

_JOB_PROGRESS = {}

# 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€ 閹煎瓨姊婚弫銈夊礆濠靛棭娼楅柛鏍垫嫹 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"
login_manager.login_message = "璇峰厛鐧诲綍鍚庡啀璁块棶璇ラ〉闈�"

# 绗﹀彿鏁版嵁搴擄紙鍚姩鏃跺姞杞藉埌鍐呭瓨锛屾悳绱㈢敤锛�
_SYMBOLS: list[dict] = []
_SYMBOLS_PATH = os.path.join(os.path.dirname(__file__), "data", "symbols.json")

_FALLBACK_SYMBOLS = [
    {"ticker": "600519", "name": "鐠愰潧绐炶寘鍙�", "market": "a_share"},
    {"ticker": "000858", "name": "浜旂伯娑�", "market": "a_share"},
    {"ticker": "300750", "name": "鐎逛礁鐥夐弮鏈靛敩", "market": "a_share"},
    {"ticker": "AAPL", "name": "閼昏鐏�", "market": "us_stock"},
    {"ticker": "MSFT", "name": "寰蒋", "market": "us_stock"},
    {"ticker": "NVDA", "name": "鑻变紵杈�", "market": "us_stock"},
    {"ticker": "00700", "name": "鑵捐鎺ц偂", "market": "hk_stock"},
    {"ticker": "09988", "name": "闂冨潡鍣峰鏉戝弽-W", "market": "hk_stock"},
]


def _load_symbols():
    global _SYMBOLS
    if os.path.exists(_SYMBOLS_PATH):
        try:
            with open(_SYMBOLS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data:
                _SYMBOLS = data
                app_logger.info(f"绗﹀彿鏁版嵁搴撳凡鍔犺浇: {len(_SYMBOLS)} 鏉�")
                return
        except Exception as e:
            app_logger.warning(f"绗﹀彿鏁版嵁搴撹鍙栧け璐�: {e}")
    app_logger.warning("绗﹀彿鏁版嵁搴撲笉瀛樺湪鎴栦负绌猴紝浣跨敤鍐呯疆 fallback")
    _SYMBOLS = list(_FALLBACK_SYMBOLS)


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€ 鍋ュ悍妫€鏌� 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

@app.route("/api/health")
def health():
    """澧炲己鍨嬪仴搴锋鏌ワ細鏁版嵁搴撱€佺鍙峰簱銆佺鐩樸€�"""
    checks = {"db": False, "symbols": False}
    try:
        db.session.execute(db.text("SELECT 1"))
        checks["db"] = True
    except Exception:
        pass
    checks["symbols"] = len(_SYMBOLS) > 0
    checks["symbols_count"] = len(_SYMBOLS)

    all_ok = all([checks["db"], checks["symbols"]])
    return jsonify(
        status="ok" if all_ok else "degraded",
        time=datetime.now().isoformat(),
        checks=checks,
    ), 200 if all_ok else 503


@app.route("/api/market-overview")
@login_required
def api_market_overview():
    """杩斿洖涓昏甯傚満鎸囨暟琛屾儏"""
    indices = []
    try:
        import akshare as ak
        spot = ak.stock_zh_index_spot_em()
        targets = {
            "娑撳﹨鐦夐幐鍥ㄦ殶": "娑撳﹨鐦�",
            "濞ｈ精鐦夐幋鎰瘹": "濞ｈ精鐦�",
            "鍒涗笟鏉挎寚": "閸掓稐绗熸潯",
        }
        for _, row in spot.iterrows():
            name = str(row.get("閸氬秶袨", ""))
            if name in targets:
                try:
                    indices.append({
                        "name": targets[name],
                        "price": round(float(row.get("閺堚偓閺傞鐜�", 0)), 2),
                        "change_pct": round(float(row.get("娑ㄨ穼骞�", 0)), 2),
                    })
                except (ValueError, TypeError):
                    pass
    except Exception as e:
        app_logger.warning(f"A鑲℃寚鏁拌幏鍙栧け璐�: {e}")

    try:
        import yfinance as yf
        us_hk = {
            "^IXIC": "缁捐櫕鏌夋潏鎯у帬",
            "^GSPC": "閺嶅洦娅�500",
            "^HSI": "閹帞鏁�",
        }
        for symbol, label in us_hk.items():
            try:
                t = yf.Ticker(symbol)
                info = t.fast_info
                price = getattr(info, "last_price", None) or getattr(info, "previous_close", None)
                prev = getattr(info, "previous_close", None) or getattr(info, "regular_market_previous_close", None)
                if price and prev and prev > 0:
                    pct = (price - prev) / prev * 100
                    indices.append({
                        "name": label,
                        "price": round(float(price), 2),
                        "change_pct": round(float(pct), 2),
                    })
            except Exception:
                pass
    except Exception as e:
        app_logger.warning(f"缇�/娓寚鏁拌幏鍙栧け璐�: {e}")

    return jsonify(indices)



# 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€ 閴存潈璺敱 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")
        if not username or not password:
            flash("鐢ㄦ埛閸氬秴鎷扮€靛棛鐖滄稉宥堝厴娑撹櫣鈹�", "danger")
            return redirect(url_for("register"))
        if len(password) < 6:
            flash("瀵嗙爜闀垮害涓嶈兘灏戜簬 6 浣�", "danger")
            return redirect(url_for("register"))
        if password != confirm:
            flash("涓ゆ杈撳叆鐨勫瘑鐮佷笉涓€鑷�", "danger")
            return redirect(url_for("register"))
        if User.query.filter_by(username=username).first():
            flash("璇ョ敤鎴峰悕宸茶娉ㄥ唽", "danger")
            return redirect(url_for("register"))
        user = User(username=username)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        app_logger.info(f"鏂扮敤鎴锋敞鍐�: {username}")
        flash("娉ㄥ唽鎴愬姛锛岃鐧诲綍", "success")
        return redirect(url_for("login"))
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user, remember=True)
            app_logger.info(f"鐢ㄦ埛鐧诲綍: {username}")
            return redirect(request.args.get("next") or url_for("dashboard"))
        app_logger.warning(f"鐧诲綍澶辫触: {username}")
        flash("鐢ㄦ埛鍚嶆垨瀵嗙爜閿欒顕�", "danger")
        return redirect(url_for("login"))
    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    app_logger.info(f"鐢ㄦ埛閫€鍑�: {current_user.username}")
    logout_user()
    flash("宸插畨鍏ㄩ€€鍑虹櫥褰�", "info")
    return redirect(url_for("login"))


# 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€ 椤甸潰璺敱 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

@app.route("/")
@login_required
def dashboard():
    return render_template("dashboard.html")


@app.route("/history")
@login_required
def history():
    return render_template("history.html")


@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "save":
            bot_token = request.form.get("tg_bot_token", "").strip()
            chat_id = request.form.get("tg_chat_id", "").strip()
            current_user.set_tg_config(bot_token, chat_id)
            db.session.commit()
            app_logger.info(f"鐢ㄦ埛 {current_user.username} 鏇存柊浜� Telegram 閰嶇疆")
            flash("Telegram 閰嶇疆宸蹭繚瀛橈紙宸插姞瀵嗗瓨鍌級", "success")
        elif action == "test":
            if not current_user.tg_configured:
                flash("璇峰厛淇濆瓨 Bot Token 鍜� Chat ID", "warning")
                return redirect(url_for("settings"))
            try:
                token, chat_id = current_user.get_tg_config()
                ok, msg = test_notify(token, chat_id)
                flash(msg, "success" if ok else "danger")
            except Exception as e:
                app_logger.error(f"Telegram 娴嬭瘯澶辫触: {e}")
                flash(f"閰嶇疆瑙ｅ瘑澶辫触锛岃閲嶆柊淇濆瓨: {e}", "danger")
        return redirect(url_for("settings"))

    token_display, chat_id_display = "", ""
    if current_user.tg_configured:
        try:
            t, c = current_user.get_tg_config()
            token_display = t[:10] + "****" + t[-4:] if len(t) > 14 else "******"
            chat_id_display = c
        except Exception:
            token_display = "(瑙ｅ瘑澶辫触锛岃閲嶆柊淇濆瓨)"

    return render_template("settings.html", token_display=token_display, chat_id_display=chat_id_display)


# 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€ API: 绗﹀彿鎼滅储 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

@app.route("/api/search")
@login_required
def api_search():
    """
    TradingView 椋庢牸鎼滅储锛�?q=鑼呭彴&market=a_share
    market 鍙€夛紝涓嶄紶鍒欐悳鍏ㄩ儴甯傚満
    """
    q = request.args.get("q", "").strip().lower()
    market = request.args.get("market", "")
    if len(q) < 1:
        return jsonify([])

    results = []
    for s in _SYMBOLS:
        if market and s["market"] != market:
            continue
        if q in s["ticker"].lower() or q in s["name"].lower():
            results.append(s)
        if len(results) >= 20:
            break
    return jsonify(results)


# 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€ API: 鑷€夌鐞� 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

@app.route("/api/watchlist", methods=["GET"])
@login_required
def api_watchlist_get():
    """鑾峰彇褰撳墠鐢ㄦ埛鐨勮嚜閫夊垪琛�"""
    items = Watchlist.query.filter_by(user_id=current_user.id).order_by(Watchlist.added_at.desc()).all()
    return jsonify([
        {"id": w.id, "ticker": w.ticker, "name": w.name, "market": w.market}
        for w in items
    ])


@app.route("/api/watchlist", methods=["POST"])
@login_required
def api_watchlist_add():
    """娣诲姞鑷€�"""
    data = request.get_json(silent=True) or {}
    ticker = data.get("ticker", "").strip()
    name = data.get("name", "").strip()
    market = data.get("market", "").strip()
    if not ticker or not market:
        return jsonify(error="鍙傛暟涓嶅畬鏁�"), 400

    existing = Watchlist.query.filter_by(user_id=current_user.id, ticker=ticker, market=market).first()
    if existing:
        return jsonify(error="宸插湪鑷€変腑"), 409

    w = Watchlist(user_id=current_user.id, ticker=ticker, name=name, market=market)
    db.session.add(w)
    db.session.commit()
    app_logger.info(f"鐢ㄦ埛 {current_user.username} 娣诲姞鑷€�: {market}:{ticker}")
    return jsonify(id=w.id, ticker=w.ticker, name=w.name, market=w.market), 201


@app.route("/api/watchlist/<int:item_id>", methods=["DELETE"])
@login_required
def api_watchlist_delete(item_id):
    """鍒犻櫎鑷€�"""
    w = Watchlist.query.filter_by(id=item_id, user_id=current_user.id).first()
    if not w:
        return jsonify(error="鏈壘鍒�"), 404
    db.session.delete(w)
    db.session.commit()
    app_logger.info(f"鐢ㄦ埛 {current_user.username} 鍒犻櫎鑷€�: {w.market}:{w.ticker}")
    return jsonify(status="deleted")


# 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€ API: 鑷€夎鎯� 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

@app.route("/api/watchlist/quotes")
@login_required
def api_watchlist_quotes():
    """鑾峰彇鑷€夊垪琛ㄧ殑瀹炴椂琛屾儏"""
    items = Watchlist.query.filter_by(user_id=current_user.id).all()
    if not items:
        return jsonify([])

    from data.market_data import get_quotes_batch
    quote_input = [{"ticker": w.ticker, "market": w.market, "name": w.name} for w in items]
    quotes = get_quotes_batch(quote_input)

    # 鐢ㄨ嚜閫夎〃鐨� name 琛ュ厖锛坹finance 鍙兘缂轰腑鏂囧悕锛�
    name_map = {(w.ticker, w.market): w.name for w in items}
    id_map = {(w.ticker, w.market): w.id for w in items}
    for q in quotes:
        key = (q["ticker"], q["market"])
        if not q.get("name") and key in name_map:
            q["name"] = name_map[key]
        q["watchlist_id"] = id_map.get(key)

    if request.args.get("sparkline") == "1":
        from data.market_data import get_recent_prices
        for q in quotes:
            try:
                prices = get_recent_prices(q["ticker"], q["market"], 20)
                q["sparkline"] = [round(float(p), 2) for p in prices] if prices else []
            except Exception:
                q["sparkline"] = []

    return jsonify(quotes)


# 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€ API: 濮ｅ繑妫╂姤鍛� 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

@app.route("/api/report")
@login_required
def api_report():
    """
    鑾峰彇鎸囧畾甯傚満鐨勬瘡鏃ユ姤鍛婏細?market=a_share&date=2026-03-11
    涓嶄紶 date 榛樿杩斿洖鏈€鏂颁竴鏈�
    """
    market = request.args.get("market", "a_share")
    date_str = request.args.get("date", "")

    if date_str:
        try:
            target_date = date.fromisoformat(date_str)
        except ValueError:
            return jsonify(error="鏃ユ湡鏍煎紡閿欒"), 400
        report = DailyReport.query.filter_by(market=market, report_date=target_date).first()
    else:
        report = DailyReport.query.filter_by(market=market).order_by(DailyReport.report_date.desc()).first()

    if not report:
        return jsonify(data=None, message="鏆傛棤鎶ュ憡")

    return jsonify(
        market=report.market,
        report_date=report.report_date.isoformat(),
        generated_at=report.generated_at.isoformat(),
        data=json.loads(report.data),
    )


# 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€ API: 鎵嬪姩鐢熸垚鎶ュ憡 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

@app.route("/api/report/generate", methods=["POST"])
@login_required
def api_report_generate():
    """寮傛瑙﹀彂鎶ュ憡鐢熸垚锛岃繑鍥� job_id 渚涘墠绔疆璇€€�"""
    import uuid
    data = request.get_json(silent=True) or {}
    market = data.get("market", "a_share")
    use_screener = bool(data.get("use_screener", False))
    use_news = bool(data.get("use_news", False))
    valid_markets = {"a_share", "us_stock", "hk_stock", "fund"}
    if market not in valid_markets:
        return jsonify(error="鏃犳晥鐨勫競鍦哄弬鏁�"), 400

    job_id = str(uuid.uuid4())
    from models import ReportJob
    job = ReportJob(
        job_id=job_id,
        user_id=current_user.id,
        market=market,
        status="pending",
        progress=0,
        progress_msg="浠诲姟宸叉彁浜わ紝绛夊緟鎵ц...",
    )
    db.session.add(job)
    db.session.commit()

    import threading
    t = threading.Thread(
        target=_run_report_job,
        args=(app, job_id, market, use_screener, use_news),
        daemon=True,
    )
    t.start()
    return jsonify(status="ok", job_id=job_id)


@app.route("/api/report/job/<job_id>")
@login_required
def api_report_job_status(job_id):
    """\u67e5\u8be2\u62a5\u544a\u751f\u6210\u4efb\u52a1\u72b6\u6001\uff0c\u542b\u8be6\u7ec6\u8fdb\u5ea6\u3002"""
    from models import ReportJob
    job = ReportJob.query.filter_by(job_id=job_id).first()
    if not job:
        return jsonify(error="\u4efb\u52a1\u4e0d\u5b58\u5728"), 404
    result = {
        "job_id": job.job_id,
        "status": job.status,
        "progress": job.progress,
        "progress_msg": job.progress_msg,
        "error_type": job.error_type,
        "error_msg": job.error_msg,
    }
    detail = _JOB_PROGRESS.get(job_id)
    if detail:
        result["current_ticker"] = detail.get("ticker")
        result["current_name"] = detail.get("name")
        result["total"] = detail.get("total")
        result["completed"] = detail.get("completed")
        result["success_count"] = detail.get("success_count", 0)
        result["failed_count"] = detail.get("failed_count", 0)
    if job.status in ("done", "partial") and job.report_id:
        result["report_id"] = job.report_id
    return jsonify(**result)


def _run_report_job(flask_app, job_id, market, use_screener, use_news):
    """后台线程执行报告生成，带详细进度跟踪。"""
    import time as _time
    with flask_app.app_context():
        from models import ReportJob
        job = ReportJob.query.filter_by(job_id=job_id).first()
        if not job:
            return
        try:
            job.status = "running"
            job.progress = 5
            job.progress_msg = "正在获取股票池..."
            db.session.commit()
            _JOB_PROGRESS[job_id] = {"total": 0, "completed": 0, "ticker": "", "name": ""}

            def _on_progress(info):
                pct = int(10 + 70 * info["completed"] / max(info["total"], 1))
                _JOB_PROGRESS[job_id] = info
                try:
                    job.progress = pct
                    nm = info['name']
                    tk = info['ticker']
                    comp = info['completed']
                    tot = info['total']
                    job.progress_msg = f"分析 {nm}({tk}) ({comp}/{tot})"
                    db.session.commit()
                except Exception:
                    pass

            started_at = _time.time()
            from analysis.report_generator import generate_report
            report_data = generate_report(
                market, use_screener=use_screener, use_news=use_news,
                progress_cb=_on_progress,
            )

            job.progress = 85
            job.progress_msg = "正在保存报告..."
            db.session.commit()

            today = date.today()
            existing = DailyReport.query.filter_by(market=market, report_date=today).first()
            if existing:
                existing.data = json.dumps(report_data, ensure_ascii=False)
                existing.generated_at = datetime.utcnow()
            else:
                existing = DailyReport(
                    market=market,
                    report_date=today,
                    data=json.dumps(report_data, ensure_ascii=False),
                    pushed=False,
                )
                db.session.add(existing)
            db.session.commit()

            report_obj = DailyReport.query.filter_by(market=market, report_date=today).first()
            if report_obj:
                _create_tracks(report_obj, report_data)
                job.report_id = report_obj.id

            elapsed = round(_time.time() - started_at, 2)
            items = report_data.get("items", [])
            total_tickers = report_data.get("total_tickers", 0)
            failed_tickers = report_data.get("failed_tickers", [])

            if not items:
                job.status = "failed"
                job.error_type = "empty"
                fail_errors = set(f.get("error", "") for f in failed_tickers)
                if any("timeout" in e.lower() for e in fail_errors):
                    job.error_msg = (
                        f"所有 {total_tickers} 只标的分析均失败（数据源超时）。"
                        "服务器在海外，访问中国数据源可能受限。"
                    )
                else:
                    job.error_msg = f"所有 {total_tickers} 只标的分析均失败。请检查数据源可用性。"
                job.progress = 100
                job.progress_msg = "生成失败：所有标的分析均未返回有效数据"
            elif failed_tickers:
                job.status = "partial"
                job.progress = 100
                n_ok = len(items)
                n_fail = len(failed_tickers)
                job.progress_msg = f"部分完成：{n_ok}/{total_tickers} 只标的成功，{n_fail} 只失败，耗时 {elapsed}s"
            else:
                job.status = "done"
                job.progress = 100
                n_items = len(items)
                job.progress_msg = f"报告生成完成，共 {n_items} 只标的，耗时 {elapsed}s"

            job.finished_at = datetime.utcnow()
            db.session.commit()
            n_ok = len(items)
            app_logger.info(f"[报告] 异步生成 {market} 完成，{n_ok}/{total_tickers} 成功，耗时 {elapsed}s")

        except Exception as e:
            import traceback
            from utils.data_fetcher import classify_error
            err_info = classify_error(e)
            job.status = "failed"
            job.error_type = err_info["error_type"]
            job.error_msg = f"{err_info['message']}: {e}"
            job.progress = 100
            job.progress_msg = "生成失败"
            job.finished_at = datetime.utcnow()
            db.session.commit()
            app_logger.error(f"[报告] 异步生成 {market} 失败: {traceback.format_exc()}")
        finally:
            _JOB_PROGRESS.pop(job_id, None)

# 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€ 鍚姩鍏ュ彛 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€


def _create_tracks(report_obj, report_data):
    """为报告中每条推荐创建准确率追踪记录"""
    items = report_data.get("items", [])
    for item in items:
        existing = RecommendationTrack.query.filter_by(
            report_id=report_obj.id, ticker=item["ticker"]
        ).first()
        if existing:
            continue
        track = RecommendationTrack(
            report_id=report_obj.id,
            ticker=item["ticker"],
            name=item["name"],
            market=item.get("market", report_obj.market),
            direction=item["direction"],
            entry_price=item.get("price_raw") or item["entry"],
            stop_loss=item["stop_loss"],
            take_profit_1=item["take_profit_1"],
            take_profit_2=item["take_profit_2"],
            confidence=item["confidence"],
            outcome="pending",
        )
        db.session.add(track)
    db.session.commit()


# 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€ API: 鍘嗗彶鎶ュ憡鍒楄〃 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

@app.route("/api/report/history")
@login_required
def api_report_history():
    """鑾峰彇鎸囧畾甯傚満鐨勫巻鍙叉姤鍛婂垪琛紙鍙繑鍥炴憳瑕佷俊鎭紝涓嶅惈瀹屾暣鏁版嵁锛�"""
    market = request.args.get("market", "a_share")
    reports = DailyReport.query.filter_by(market=market).order_by(
        DailyReport.report_date.desc()
    ).limit(60).all()

    result = []
    for r in reports:
        try:
            data = json.loads(r.data)
            metrics = data.get("metrics", {})
        except Exception:
            metrics = {}
        result.append({
            "id": r.id,
            "report_date": r.report_date.isoformat(),
            "generated_at": r.generated_at.isoformat() if r.generated_at else None,
            "metrics": metrics,
        })
    return jsonify(result)


# 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€ API: 鍑嗙‘鐜囩粺璁� 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

@app.route("/api/accuracy")
@login_required
def api_accuracy():
    """鑾峰彇鎸囧畾甯傚満鐨勬帹鑽愬噯纭巼缁熻"""
    market = request.args.get("market", "a_share")

    tracks = RecommendationTrack.query.filter_by(market=market).all()
    total = len(tracks)
    win = sum(1 for t in tracks if t.outcome == "win")
    loss = sum(1 for t in tracks if t.outcome == "loss")
    partial = sum(1 for t in tracks if t.outcome == "partial")
    pending = sum(1 for t in tracks if t.outcome == "pending" or t.outcome is None)

    return jsonify({
        "market": market,
        "total": total,
        "win": win,
        "loss": loss,
        "partial": partial,
        "pending": pending,
        "win_rate": round(win / total * 100, 1) if total > 0 else 0,
    })


# 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€ API: LLM 鐘舵€佹鏌� 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

@app.route("/api/llm/status")
@login_required
def api_llm_status():
    """妫€鏌� LLM 鏈嶅姟杩為€氭€�"""
    from analysis.llm_client import llm_health_check
    return jsonify(llm_health_check())



# 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€ API: 涓偂娣卞害鍒嗘瀽 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

@app.route("/deep-analysis")
@login_required
def deep_analysis():
    return render_template("deep_analysis.html")

@app.route("/compare")
@login_required
def compare():
    return render_template("compare.html")




@app.route("/api/deep-analysis", methods=["POST"])
@login_required
def api_deep_analysis():
    import json as _json
    from models import DeepAnalysisCache

    data = request.get_json(silent=True) or {}
    ticker = data.get("ticker", "").strip()
    market = data.get("market", "").strip()
    force = data.get("force", False)

    if not ticker or not market:
        return jsonify(error="鍙傛暟涓嶅畬鏁�"), 400

    valid_markets = {"a_share", "us_stock", "hk_stock"}
    if market not in valid_markets:
        return jsonify(error="娣卞害鍒嗘瀽涓嶆敮鎸佽甯傚満绫诲瀷"), 400

    CACHE_TTL = 4 * 3600
    if not force:
        cached = DeepAnalysisCache.query.filter_by(
            ticker=ticker, market=market).first()
        if cached:
            age = (datetime.utcnow() - cached.created_at).total_seconds()
            if age < CACHE_TTL:
                app_logger.info(f"娣卞害鍒嗘瀽鍛戒腑缂撳瓨 {market}:{ticker}")
                return jsonify(_json.loads(cached.data))

    try:
        result = _run_deep_analysis(ticker, market)
        _save_deep_cache(ticker, market, result)
        app_logger.info(f"鐢ㄦ埛 {current_user.username} 娣卞害鍒嗘瀽 {market}:{ticker}")
        return jsonify(result)
    except Exception as e:
        app_logger.error(f"娣卞害鍒嗘瀽澶辫触 {market}:{ticker}: {e}")
        return jsonify(error=str(e)), 500




UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


@app.route("/api/upload-report", methods=["POST"])
@login_required
def api_upload_report():
    """涓婁紶骞存姤 PDF锛屾彁鍙栧叧閿珷鑺備俊鎭紝鍙€夎仈鍚� LLM 鍒嗘瀽銆�"""
    from analysis.pdf_parser import parse_annual_report, format_for_llm
    from analysis.llm_client import chat_completion, _is_enabled

    if "pdf" not in request.files:
        return jsonify(error="鐠囩兘鈧瀚� PDF 閺傚洣娆�"), 400

    file = request.files["pdf"]
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        return jsonify(error="浠呮敮鎸� PDF 鏍煎紡"), 400

    save_path = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(save_path)
    app_logger.info(f"鐢ㄦ埛 {current_user.username} 涓婁紶骞存姤: {file.filename}")

    try:
        parsed = parse_annual_report(save_path)
        if not parsed:
            return jsonify(error="PDF 瑙ｆ瀽澶辫触"), 500

        llm_summary = None
        if _is_enabled() and parsed["extracted_count"] > 0:
            llm_text = format_for_llm(parsed)
            prompt = (
                "浠ヤ笅鏄竴浠� A 鑲″勾鎶ョ殑鍏抽敭绔犺妭鎻愬彇鍐呭锛岃鍋氱患鍚堝垎鏋�:\n"
                "1. 鏄惁瀛樺湪闅愭€ч闄╋紙鍙楅檺璧勪骇杩囬珮銆佸簲鏀惰处榫勮€佸寲銆佸叧鑱斾氦鏄撳紓甯哥瓑锛塡n"
                "2. 缁忚惀浜偣涓庨殣蹇n"
                "3. 涓€鍙ヨ瘽鎬荤粨璇ュ勾鎶ヨ川閲廫n\n"
                f"{llm_text}"
            )
            messages = [
                {"role": "system", "content": "浣犳槸 Alpha Vault 鐨勫勾鎶ュ垎鏋愬姪鎵嬨€�"},
                {"role": "user", "content": prompt},
            ]
            llm_summary = chat_completion(messages, max_tokens=2048)

        return jsonify({
            "file_name": parsed["file_name"],
            "total_pages": parsed["total_pages"],
            "extracted_count": parsed["extracted_count"],
            "sections": parsed["sections"],
            "llm_summary": llm_summary,
        })
    except Exception as e:
        app_logger.error(f"骞存姤鍒嗘瀽澶辫触: {e}")
        return jsonify(error=str(e)), 500
    finally:
        try:
            os.remove(save_path)
        except OSError:
            pass



@app.route("/api/deep-analysis-stream", methods=["POST"])
@login_required
def api_deep_analysis_stream():
    """SSE streaming deep analysis with step-by-step progress."""
    import json as _json
    from flask import Response

    data = request.get_json(silent=True) or {}
    ticker = data.get("ticker", "").strip()
    market = data.get("market", "").strip()

    if not ticker or not market:
        return jsonify(error="missing params"), 400
    if market not in {"a_share", "us_stock", "hk_stock"}:
        return jsonify(error="invalid market"), 400

    def generate():
        from analysis.technical import analyze as tech_analyze
        from analysis.news_fetcher import fetch_news, analyze_sentiment
        from analysis.fundamental import analyze as fund_analyze
        from analysis.valuation import valuate
        from data.financial import get_financial_data
        from analysis.llm_client import llm_analyze_stock, llm_cigbutt_analyze, _is_enabled

        steps_total = 6

        yield f"data: {_json.dumps({'step':1,'total':steps_total,'msg':'鑾峰彇琛屾儏鏁版嵁...'}, ensure_ascii=False)}\n\n"
        tech = tech_analyze(ticker, market)

        yield f"data: {_json.dumps({'step':2,'total':steps_total,'msg':'鍒嗘瀽鎶€鏈潰...'}, ensure_ascii=False)}\n\n"
        news = fetch_news(ticker, market, limit=10)
        sentiment = analyze_sentiment(news)

        yield f"data: {_json.dumps({'step':3,'total':steps_total,'msg':'鍒嗘瀽鍩烘湰闈�...'}, ensure_ascii=False)}\n\n"
        fund_data = None
        try:
            fund_data = fund_analyze(ticker, market)
        except Exception as e:
            app_logger.warning(f"SSE deep - fundamental fail {ticker}: {e}")

        yield f"data: {_json.dumps({'step':4,'total':steps_total,'msg':'浼板€煎垎鏋�...'}, ensure_ascii=False)}\n\n"
        val_data = None
        if fund_data and tech:
            try:
                fin = get_financial_data(ticker, market)
                if fin:
                    val_data = valuate(fin, tech["price"])
            except Exception as e:
                app_logger.warning(f"SSE deep - valuation fail {ticker}: {e}")

        yield f"data: {_json.dumps({'step':5,'total':steps_total,'msg':'AI 鐮斿垽涓�...'}, ensure_ascii=False)}\n\n"
        llm_result = None
        cigbutt_result = None
        if _is_enabled():
            try:
                llm_result = llm_analyze_stock(
                    ticker, "", market, tech or {}, news,
                    fundamental_data=fund_data, valuation_data=val_data)
            except Exception as e:
                app_logger.warning(f"SSE deep - LLM fail {ticker}: {e}")
            if market == "a_share" and val_data and val_data.get("cigbutt"):
                try:
                    cigbutt_result = llm_cigbutt_analyze(ticker, "", fund_data, val_data)
                except Exception:
                    pass

        result = {
            "ticker": ticker, "market": market,
            "technical": tech,
            "news": {"items": news, "sentiment": sentiment},
            "fundamental": fund_data,
            "valuation": val_data,
            "llm_analysis": llm_result,
            "cigbutt_analysis": cigbutt_result,
            "generated_at": datetime.now().isoformat(),
        }

        try:
            fin_for_chart = get_financial_data(ticker, market)
            result["chart_data"] = _build_chart_data(fin_for_chart, val_data)
        except Exception:
            result["chart_data"] = None

        _save_deep_cache(ticker, market, result)

        yield f"data: {_json.dumps({'step':6,'total':steps_total,'msg':'瀹屾垚','done':True,'result':result}, ensure_ascii=False, default=str)}\n\n"

    return Response(generate(), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


def _save_deep_cache(ticker: str, market: str, result: dict):
    import json as _json
    from models import DeepAnalysisCache
    try:
        existing = DeepAnalysisCache.query.filter_by(
            ticker=ticker, market=market).first()
        if existing:
            existing.data = _json.dumps(result, ensure_ascii=False, default=str)
            existing.created_at = datetime.utcnow()
        else:
            cache = DeepAnalysisCache(
                ticker=ticker, market=market,
                data=_json.dumps(result, ensure_ascii=False, default=str))
            db.session.add(cache)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        app_logger.warning(f"娣卞害鍒嗘瀽缂撳瓨淇濆瓨澶辫触: {e}")



# ======================== API: 鍛婅瑙勫垯 CRUD ========================

@app.route("/api/alerts", methods=["GET"])
@login_required
def api_alerts_list():
    rules = AlertRule.query.filter_by(user_id=current_user.id).order_by(AlertRule.created_at.desc()).all()
    return jsonify([{
        "id": r.id, "ticker": r.ticker, "name": r.name, "market": r.market,
        "rule_type": r.rule_type, "threshold": r.threshold,
        "enabled": r.enabled,
        "type_label": AlertRule.RULE_TYPES.get(r.rule_type, r.rule_type),
        "last_triggered": r.last_triggered.isoformat() if r.last_triggered else None,
        "created_at": r.created_at.isoformat(),
    } for r in rules])


@app.route("/api/alerts", methods=["POST"])
@login_required
def api_alerts_create():
    data = request.get_json(silent=True) or {}
    ticker = data.get("ticker", "").strip()
    market = data.get("market", "").strip()
    rule_type = data.get("rule_type", "").strip()
    threshold = data.get("threshold")
    name = data.get("name", "")

    if not ticker or not market or not rule_type:
        return jsonify(error="missing params"), 400
    if rule_type not in AlertRule.RULE_TYPES:
        return jsonify(error="invalid rule_type"), 400
    if threshold is None:
        return jsonify(error="missing threshold"), 400

    rule = AlertRule(
        user_id=current_user.id, ticker=ticker, name=name,
        market=market, rule_type=rule_type, threshold=float(threshold)
    )
    db.session.add(rule)
    db.session.commit()
    return jsonify(id=rule.id, msg="created"), 201


@app.route("/api/alerts/<int:rule_id>", methods=["PUT"])
@login_required
def api_alerts_update(rule_id):
    rule = AlertRule.query.filter_by(id=rule_id, user_id=current_user.id).first()
    if not rule:
        return jsonify(error="not found"), 404
    data = request.get_json(silent=True) or {}
    if "enabled" in data:
        rule.enabled = bool(data["enabled"])
    if "threshold" in data:
        rule.threshold = float(data["threshold"])
    if "rule_type" in data and data["rule_type"] in AlertRule.RULE_TYPES:
        rule.rule_type = data["rule_type"]
    db.session.commit()
    return jsonify(msg="updated")


@app.route("/api/alerts/<int:rule_id>", methods=["DELETE"])
@login_required
def api_alerts_delete(rule_id):
    rule = AlertRule.query.filter_by(id=rule_id, user_id=current_user.id).first()
    if not rule:
        return jsonify(error="not found"), 404
    db.session.delete(rule)
    db.session.commit()
    return jsonify(msg="deleted")



# ======================== API: 缁╂晥缁熻顓� ========================

@app.route("/api/performance")
@login_required
def api_performance():
    """缁熻鎺ㄨ崘缁╂晥锛氳儨鐜囥€佺泩浜忔瘮銆佸钩鍧囨敹鐩娿€佹寜鏃ヨ蛋鍔裤€�"""
    market = request.args.get("market", "a_share")
    days = int(request.args.get("days", "90"))

    from datetime import timedelta
    cutoff = date.today() - timedelta(days=days)

    tracks = RecommendationTrack.query.join(DailyReport).filter(
        DailyReport.market == market,
        DailyReport.report_date >= cutoff,
    ).all()

    total = len(tracks)
    if total == 0:
        return jsonify({
            "total": 0, "win": 0, "loss": 0, "pending": 0,
            "win_rate": 0, "avg_return": 0, "max_win": 0, "max_loss": 0,
            "profit_factor": 0, "daily_stats": [], "recent": [],
        })

    wins, losses, pending_count = 0, 0, 0
    returns = []
    win_amounts, loss_amounts = [], []

    for t in tracks:
        if t.outcome == "win" or t.outcome == "partial":
            wins += 1
            final_price = t.price_after_5d or t.price_after_3d or t.price_after_1d or t.entry_price
            ret = ((final_price - t.entry_price) / t.entry_price * 100) if t.entry_price else 0
            if t.direction == "sell":
                ret = -ret
            returns.append(ret)
            win_amounts.append(abs(ret))
        elif t.outcome == "loss":
            losses += 1
            final_price = t.price_after_5d or t.price_after_3d or t.price_after_1d or t.entry_price
            ret = ((final_price - t.entry_price) / t.entry_price * 100) if t.entry_price else 0
            if t.direction == "sell":
                ret = -ret
            returns.append(ret)
            loss_amounts.append(abs(ret))
        else:
            pending_count += 1

    decided = wins + losses
    win_rate = round(wins / decided * 100, 1) if decided > 0 else 0
    avg_return = round(sum(returns) / len(returns), 2) if returns else 0
    max_win = round(max(returns), 2) if returns else 0
    max_loss = round(min(returns), 2) if returns else 0
    avg_win = sum(win_amounts) / len(win_amounts) if win_amounts else 0
    avg_loss = sum(loss_amounts) / len(loss_amounts) if loss_amounts else 1
    profit_factor = round(avg_win / avg_loss, 2) if avg_loss > 0 else 0

    daily_map = {}
    for t in tracks:
        report = DailyReport.query.get(t.report_id)
        if not report:
            continue
        d = report.report_date.isoformat()
        if d not in daily_map:
            daily_map[d] = {"date": d, "win": 0, "loss": 0, "total": 0}
        daily_map[d]["total"] += 1
        if t.outcome in ("win", "partial"):
            daily_map[d]["win"] += 1
        elif t.outcome == "loss":
            daily_map[d]["loss"] += 1
    daily_stats = sorted(daily_map.values(), key=lambda x: x["date"])
    for ds in daily_stats:
        decided_d = ds["win"] + ds["loss"]
        ds["win_rate"] = round(ds["win"] / decided_d * 100, 1) if decided_d > 0 else 0

    recent = []
    for t in sorted(tracks, key=lambda x: x.created_at or datetime.min, reverse=True)[:10]:
        final_price = t.price_after_5d or t.price_after_3d or t.price_after_1d
        ret_pct = 0
        if final_price and t.entry_price:
            ret_pct = round((final_price - t.entry_price) / t.entry_price * 100, 2)
            if t.direction == "sell":
                ret_pct = -ret_pct
        recent.append({
            "ticker": t.ticker, "name": t.name, "market": t.market,
            "direction": t.direction, "outcome": t.outcome or "pending",
            "return_pct": ret_pct,
            "entry_price": t.entry_price,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        })

    return jsonify({
        "total": total, "win": wins, "loss": losses, "pending": pending_count,
        "win_rate": win_rate, "avg_return": avg_return,
        "max_win": max_win, "max_loss": max_loss,
        "profit_factor": profit_factor,
        "daily_stats": daily_stats,
        "recent": recent,
    })


# ======================== API: 婢舵俺鍋傜€佃鐦� ========================

@app.route("/api/compare", methods=["POST"])
@login_required
def api_compare():
    """瀵规瘮 2-4 鍙偂绁ㄧ殑鍩烘湰闈�/浼板€�/鎶€鏈潰銆�"""
    data = request.get_json(silent=True) or {}
    tickers = data.get("tickers", [])

    if not tickers or len(tickers) < 2 or len(tickers) > 4:
        return jsonify(error="need 2-4 tickers"), 400

    from analysis.technical import analyze as tech_analyze
    from analysis.fundamental import analyze as fund_analyze
    from analysis.valuation import valuate
    from data.financial import get_financial_data

    results = []
    for item in tickers:
        ticker = item.get("ticker", "").strip()
        market = item.get("market", "").strip()
        if not ticker or not market:
            continue

        entry = {"ticker": ticker, "market": market, "name": item.get("name", ticker)}
        try:
            tech = tech_analyze(ticker, market)
            entry["price"] = tech.get("price") if tech else None
            entry["signal"] = tech.get("signal", "neutral") if tech else "N/A"
            entry["rsi"] = tech.get("rsi") if tech else None
        except Exception:
            entry["price"] = None
            entry["signal"] = "N/A"

        try:
            fund = fund_analyze(ticker, market)
            if fund:
                entry["quality_score"] = fund.get("quality_score")
                entry["roe"] = fund.get("roe")
                entry["gross_margin"] = fund.get("gross_margin")
                entry["debt_ratio"] = fund.get("debt_ratio")
                entry["revenue_growth"] = fund.get("revenue_growth")
        except Exception:
            pass

        try:
            fin = get_financial_data(ticker, market)
            if fin and entry.get("price"):
                val = valuate(fin, entry["price"])
                if val:
                    entry["pe_ttm"] = val.get("pe_ttm")
                    entry["pb"] = val.get("pb")
                    entry["safety_margin"] = val.get("safety_margin")
                    entry["penetration_return"] = val.get("penetration_return")
        except Exception:
            pass

        results.append(entry)

    return jsonify(results)



@app.route("/api/weekly-report")
@login_required
def api_weekly_report():
    """鑾峰彇鏈€鏂板懆鎶ワ紙浠庣紦瀛樻垨瀹炴椂鐢熸垚锛夈€�"""
    market = request.args.get("market", "a_share")
    cache_key = f"weekly_{market}"

    cached = app.config.get("_weekly_cache", {}).get(cache_key)
    if cached:
        return jsonify(cached)

    try:
        from analysis.report_generator import generate_weekly_report
        report = generate_weekly_report(market)
        app.config.setdefault("_weekly_cache", {})[cache_key] = report
        return jsonify(report)
    except Exception as e:
        app_logger.warning(f"鍛ㄦ姤鐢熸垚澶辫触: {e}")
        return jsonify(content=None), 404


def _build_chart_data(fin_data, val_data):
    """Extract multi-year series from financial data for Chart.js."""
    if not fin_data or not fin_data.get("indicators"):
        return None
    indicators = fin_data["indicators"]
    indicators_sorted = sorted(indicators, key=lambda x: x.get("year", 0))
    chart = {
        "years": [str(d.get("year", "")) for d in indicators_sorted],
        "roe": [d.get("roe") for d in indicators_sorted],
        "gross_margin": [d.get("gross_margin") for d in indicators_sorted],
        "net_margin": [d.get("net_margin") for d in indicators_sorted],
        "revenue_growth": [d.get("revenue_growth") for d in indicators_sorted],
        "profit_growth": [d.get("profit_growth") for d in indicators_sorted],
        "debt_ratio": [d.get("debt_ratio") for d in indicators_sorted],
        "current_ratio": [d.get("current_ratio") for d in indicators_sorted],
    }
    if val_data:
        chart["valuation"] = {
            "current_price": val_data.get("current_price"),
            "ncav_per_share": val_data.get("ncav_per_share"),
            "bvps": val_data.get("bvps"),
            "target_price": val_data.get("target_price"),
            "pe_ttm": val_data.get("pe_ttm"),
            "pb": val_data.get("pb"),
        }
    return chart


def _run_deep_analysis(ticker: str, market: str) -> dict:
    from analysis.technical import analyze as tech_analyze
    from analysis.news_fetcher import fetch_news, analyze_sentiment
    from analysis.fundamental import analyze as fund_analyze
    from analysis.valuation import valuate
    from data.financial import get_financial_data
    from analysis.llm_client import llm_analyze_stock, llm_cigbutt_analyze, _is_enabled

    tech = tech_analyze(ticker, market)
    news = fetch_news(ticker, market, limit=10)
    sentiment = analyze_sentiment(news)

    fund_data = None
    val_data = None
    try:
        fund_data = fund_analyze(ticker, market)
    except Exception as e:
        app_logger.warning(f"娣卞害鍒嗘瀽-鍩烘湰闈㈠け璐� {ticker}: {e}")

    if fund_data and tech:
        try:
            fin = get_financial_data(ticker, market)
            if fin:
                val_data = valuate(fin, tech["price"])
        except Exception as e:
            app_logger.warning(f"娣卞害鍒嗘瀽-浼板€煎け璐� {ticker}: {e}")

    llm_result = None
    cigbutt_result = None
    if _is_enabled():
        try:
            ann_data = None
            flow_data = None
            try:
                from data.announcement import fetch_announcements
                ann_data = fetch_announcements(ticker, market)
            except Exception:
                pass
            try:
                from data.fund_flow import get_fund_flow
                flow_data = get_fund_flow(ticker, market)
            except Exception:
                pass
            llm_result = llm_analyze_stock(
                ticker, "", market, tech or {}, news,
                fundamental_data=fund_data, valuation_data=val_data,
                announcements=ann_data, fund_flow=flow_data)
        except Exception as e:
            app_logger.warning(f"娣卞害鍒嗘瀽-LLM澶辫触 {ticker}: {e}")

        if market == "a_share" and val_data and val_data.get("cigbutt"):
            try:
                cigbutt_result = llm_cigbutt_analyze(
                    ticker, "", fund_data, val_data)
            except Exception as e:
                app_logger.warning(f"娣卞害鍒嗘瀽-鐑熻拏鑲″垎鏋愬け璐� {ticker}: {e}")

    fin_for_chart = None
    try:
        fin_for_chart = get_financial_data(ticker, market)
    except Exception:
        pass
    chart_data = _build_chart_data(fin_for_chart, val_data)

    return {
        "ticker": ticker,
        "market": market,
        "technical": tech,
        "news": {"items": news, "sentiment": sentiment},
        "fundamental": fund_data,
        "valuation": val_data,
        "llm_analysis": llm_result,
        "cigbutt_analysis": cigbutt_result,
        "chart_data": chart_data,
        "generated_at": datetime.now().isoformat(),
    }


from utils.logger import init_request_logging
init_request_logging(app)

_app_initialized = False


def initialize_app():
    """缁熶竴鍒濆鍖栧叆鍙ｏ紝鍏煎 Flask 寮€鍙戞ā寮忓拰 Gunicorn銆�"""
    global _app_initialized
    if _app_initialized:
        return

    with app.app_context():
        db.create_all()
        _load_symbols()

    try:
        from scripts.scheduler import init_scheduler
        init_scheduler(app)
    except Exception as e:
        app_logger.warning(f"璋冨害鍣ㄥ惎鍔ㄥけ璐�: {e}")

    app_logger.info("Alpha Vault 鍚姩")
    _app_initialized = True


initialize_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
