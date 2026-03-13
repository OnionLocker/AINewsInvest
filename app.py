"""
app.py - Alpha Vault 涓诲簲鐢�

璺敱锛�
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
from models import db, User, Watchlist, DailyReport, RecommendationTrack
from utils.logger import app_logger
from utils.notifier import test_notify

# 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€ 搴旂敤鍒濆鍖� 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

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


def _load_symbols():
    global _SYMBOLS
    if os.path.exists(_SYMBOLS_PATH):
        with open(_SYMBOLS_PATH, "r", encoding="utf-8") as f:
            _SYMBOLS = json.load(f)
        app_logger.info(f"绗﹀彿鏁版嵁搴撳凡鍔犺浇: {len(_SYMBOLS)} 鏉�")
    else:
        app_logger.warning(f"绗﹀彿鏁版嵁搴撲笉瀛樺湪: {_SYMBOLS_PATH}锛屾悳绱㈠姛鑳藉皢涓嶅彲鐢�")


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€ 鍋ュ悍妫€鏌� 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

@app.route("/api/health")
def health():
    return jsonify(status="ok", time=datetime.now().isoformat())


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
            flash("鐢ㄦ埛鍚嶅拰瀵嗙爜涓嶈兘涓虹┖", "danger")
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
        flash("鐢ㄦ埛鍚嶆垨瀵嗙爜閿欒", "danger")
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

    return jsonify(quotes)


# 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€ API: 姣忔棩鎶ュ憡 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

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
    """鎵嬪姩瑙﹀彂鎶ュ憡鐢熸垚锛堝墠绔�"绔嬪嵆鐢熸垚"鎸夐挳锛�"""
    data = request.get_json(silent=True) or {}
    market = data.get("market", "a_share")
    valid_markets = {"a_share", "us_stock", "hk_stock", "fund"}
    if market not in valid_markets:
        return jsonify(error="鏃犳晥鐨勫競鍦哄弬鏁�"), 400

    try:
        from analysis.report_generator import generate_report
        report_data = generate_report(market)

        today = date.today()
        existing = DailyReport.query.filter_by(market=market, report_date=today).first()
        if existing:
            existing.data = json.dumps(report_data, ensure_ascii=False)
            existing.generated_at = datetime.utcnow()
        else:
            report = DailyReport(
                market=market,
                report_date=today,
                data=json.dumps(report_data, ensure_ascii=False),
                pushed=False,
            )
            db.session.add(report)
        db.session.commit()

        report_obj = DailyReport.query.filter_by(market=market, report_date=today).first()
        if report_obj:
            _create_tracks(report_obj, report_data)

        app_logger.info(f"鐢ㄦ埛 {current_user.username} 鎵嬪姩鐢熸垚 {market} 鎶ュ憡")
        return jsonify(status="ok", market=market)
    except Exception as e:
        app_logger.error(f"鎵嬪姩鐢熸垚鎶ュ憡澶辫触: {e}")
        return jsonify(error=str(e)), 500


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


# ────────────────────────── API: 历史报告列表 ──────────────────────────

@app.route("/api/report/history")
@login_required
def api_report_history():
    """获取指定市场的历史报告列表（只返回摘要信息，不含完整数据）"""
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


# ────────────────────────── API: 准确率统计 ──────────────────────────

@app.route("/api/accuracy")
@login_required
def api_accuracy():
    """获取指定市场的推荐准确率统计"""
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


# ────────────────────────── API: LLM 状态检查 ──────────────────────────

@app.route("/api/llm/status")
@login_required
def api_llm_status():
    """检查 LLM 服务连通性"""
    from analysis.llm_client import llm_health_check
    return jsonify(llm_health_check())



# ────────────────────────── API: 个股深度分析 ──────────────────────────

@app.route("/deep-analysis")
@login_required
def deep_analysis():
    return render_template("deep_analysis.html")


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
        return jsonify(error="参数不完整"), 400

    valid_markets = {"a_share", "us_stock", "hk_stock"}
    if market not in valid_markets:
        return jsonify(error="深度分析不支持该市场类型"), 400

    CACHE_TTL = 4 * 3600
    if not force:
        cached = DeepAnalysisCache.query.filter_by(
            ticker=ticker, market=market).first()
        if cached:
            age = (datetime.utcnow() - cached.created_at).total_seconds()
            if age < CACHE_TTL:
                app_logger.info(f"深度分析命中缓存 {market}:{ticker}")
                return jsonify(_json.loads(cached.data))

    try:
        result = _run_deep_analysis(ticker, market)
        _save_deep_cache(ticker, market, result)
        app_logger.info(f"用户 {current_user.username} 深度分析 {market}:{ticker}")
        return jsonify(result)
    except Exception as e:
        app_logger.error(f"深度分析失败 {market}:{ticker}: {e}")
        return jsonify(error=str(e)), 500




UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


@app.route("/api/upload-report", methods=["POST"])
@login_required
def api_upload_report():
    """上传年报 PDF，提取关键章节信息，可选联合 LLM 分析。"""
    from analysis.pdf_parser import parse_annual_report, format_for_llm
    from analysis.llm_client import chat_completion, _is_enabled

    if "pdf" not in request.files:
        return jsonify(error="请选择 PDF 文件"), 400

    file = request.files["pdf"]
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        return jsonify(error="仅支持 PDF 格式"), 400

    save_path = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(save_path)
    app_logger.info(f"用户 {current_user.username} 上传年报: {file.filename}")

    try:
        parsed = parse_annual_report(save_path)
        if not parsed:
            return jsonify(error="PDF 解析失败"), 500

        llm_summary = None
        if _is_enabled() and parsed["extracted_count"] > 0:
            llm_text = format_for_llm(parsed)
            prompt = (
                "以下是一份 A 股年报的关键章节提取内容，请做综合分析:\n"
                "1. 是否存在隐性风险（受限资产过高、应收账龄老化、关联交易异常等）\n"
                "2. 经营亮点与隐忧\n"
                "3. 一句话总结该年报质量\n\n"
                f"{llm_text}"
            )
            messages = [
                {"role": "system", "content": "你是 Alpha Vault 的年报分析助手。"},
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
        app_logger.error(f"年报分析失败: {e}")
        return jsonify(error=str(e)), 500
    finally:
        try:
            os.remove(save_path)
        except OSError:
            pass


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
        app_logger.warning(f"深度分析缓存保存失败: {e}")


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
        app_logger.warning(f"深度分析-基本面失败 {ticker}: {e}")

    if fund_data and tech:
        try:
            fin = get_financial_data(ticker, market)
            if fin:
                val_data = valuate(fin, tech["price"])
        except Exception as e:
            app_logger.warning(f"深度分析-估值失败 {ticker}: {e}")

    llm_result = None
    cigbutt_result = None
    if _is_enabled():
        try:
            llm_result = llm_analyze_stock(
                ticker, "", market, tech or {}, news,
                fundamental_data=fund_data, valuation_data=val_data)
        except Exception as e:
            app_logger.warning(f"深度分析-LLM失败 {ticker}: {e}")

        if market == "a_share" and val_data and val_data.get("cigbutt"):
            try:
                cigbutt_result = llm_cigbutt_analyze(
                    ticker, "", fund_data, val_data)
            except Exception as e:
                app_logger.warning(f"深度分析-烟蒂股分析失败 {ticker}: {e}")

    return {
        "ticker": ticker,
        "market": market,
        "technical": tech,
        "news": {"items": news, "sentiment": sentiment},
        "fundamental": fund_data,
        "valuation": val_data,
        "llm_analysis": llm_result,
        "cigbutt_analysis": cigbutt_result,
        "generated_at": datetime.now().isoformat(),
    }


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        _load_symbols()
    app_logger.info("Alpha Vault 鍚姩")
    app.run(host="0.0.0.0", port=5000, debug=True)
