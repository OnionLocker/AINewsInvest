"""
app.py - Alpha Vault 主应用

路由：
  - 鉴权：/login, /register, /logout
  - 页面：/ (dashboard), /settings
  - API：/api/health, /api/search, /api/watchlist, /api/quotes, /api/report
"""
import json
import os
from datetime import datetime, date
from flask import Flask, render_template, redirect, url_for, request, flash, jsonify
from flask_login import (
    LoginManager, login_user, logout_user, login_required, current_user,
)
from config import Config
from models import db, User, Watchlist, DailyReport
from utils.logger import app_logger
from utils.notifier import test_notify

# ────────────────────────── 应用初始化 ──────────────────────────

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"
login_manager.login_message = "请先登录后再访问该页面"

# 符号数据库（启动时加载到内存，搜索用）
_SYMBOLS: list[dict] = []
_SYMBOLS_PATH = os.path.join(os.path.dirname(__file__), "data", "symbols.json")


def _load_symbols():
    global _SYMBOLS
    if os.path.exists(_SYMBOLS_PATH):
        with open(_SYMBOLS_PATH, "r", encoding="utf-8") as f:
            _SYMBOLS = json.load(f)
        app_logger.info(f"符号数据库已加载: {len(_SYMBOLS)} 条")
    else:
        app_logger.warning(f"符号数据库不存在: {_SYMBOLS_PATH}，搜索功能将不可用")


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# ────────────────────────── 健康检查 ──────────────────────────

@app.route("/api/health")
def health():
    return jsonify(status="ok", time=datetime.now().isoformat())


# ────────────────────────── 鉴权路由 ──────────────────────────

@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")
        if not username or not password:
            flash("用户名和密码不能为空", "danger")
            return redirect(url_for("register"))
        if len(password) < 6:
            flash("密码长度不能少于 6 位", "danger")
            return redirect(url_for("register"))
        if password != confirm:
            flash("两次输入的密码不一致", "danger")
            return redirect(url_for("register"))
        if User.query.filter_by(username=username).first():
            flash("该用户名已被注册", "danger")
            return redirect(url_for("register"))
        user = User(username=username)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        app_logger.info(f"新用户注册: {username}")
        flash("注册成功，请登录", "success")
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
            app_logger.info(f"用户登录: {username}")
            return redirect(request.args.get("next") or url_for("dashboard"))
        app_logger.warning(f"登录失败: {username}")
        flash("用户名或密码错误", "danger")
        return redirect(url_for("login"))
    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    app_logger.info(f"用户退出: {current_user.username}")
    logout_user()
    flash("已安全退出登录", "info")
    return redirect(url_for("login"))


# ────────────────────────── 页面路由 ──────────────────────────

@app.route("/")
@login_required
def dashboard():
    return render_template("dashboard.html")


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
            app_logger.info(f"用户 {current_user.username} 更新了 Telegram 配置")
            flash("Telegram 配置已保存（已加密存储）", "success")
        elif action == "test":
            if not current_user.tg_configured:
                flash("请先保存 Bot Token 和 Chat ID", "warning")
                return redirect(url_for("settings"))
            try:
                token, chat_id = current_user.get_tg_config()
                ok, msg = test_notify(token, chat_id)
                flash(msg, "success" if ok else "danger")
            except Exception as e:
                app_logger.error(f"Telegram 测试失败: {e}")
                flash(f"配置解密失败，请重新保存: {e}", "danger")
        return redirect(url_for("settings"))

    token_display, chat_id_display = "", ""
    if current_user.tg_configured:
        try:
            t, c = current_user.get_tg_config()
            token_display = t[:10] + "****" + t[-4:] if len(t) > 14 else "******"
            chat_id_display = c
        except Exception:
            token_display = "(解密失败，请重新保存)"

    return render_template("settings.html", token_display=token_display, chat_id_display=chat_id_display)


# ────────────────────────── API: 符号搜索 ──────────────────────────

@app.route("/api/search")
@login_required
def api_search():
    """
    TradingView 风格搜索：?q=茅台&market=a_share
    market 可选，不传则搜全部市场
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


# ────────────────────────── API: 自选管理 ──────────────────────────

@app.route("/api/watchlist", methods=["GET"])
@login_required
def api_watchlist_get():
    """获取当前用户的自选列表"""
    items = Watchlist.query.filter_by(user_id=current_user.id).order_by(Watchlist.added_at.desc()).all()
    return jsonify([
        {"id": w.id, "ticker": w.ticker, "name": w.name, "market": w.market}
        for w in items
    ])


@app.route("/api/watchlist", methods=["POST"])
@login_required
def api_watchlist_add():
    """添加自选"""
    data = request.get_json(silent=True) or {}
    ticker = data.get("ticker", "").strip()
    name = data.get("name", "").strip()
    market = data.get("market", "").strip()
    if not ticker or not market:
        return jsonify(error="参数不完整"), 400

    existing = Watchlist.query.filter_by(user_id=current_user.id, ticker=ticker, market=market).first()
    if existing:
        return jsonify(error="已在自选中"), 409

    w = Watchlist(user_id=current_user.id, ticker=ticker, name=name, market=market)
    db.session.add(w)
    db.session.commit()
    app_logger.info(f"用户 {current_user.username} 添加自选: {market}:{ticker}")
    return jsonify(id=w.id, ticker=w.ticker, name=w.name, market=w.market), 201


@app.route("/api/watchlist/<int:item_id>", methods=["DELETE"])
@login_required
def api_watchlist_delete(item_id):
    """删除自选"""
    w = Watchlist.query.filter_by(id=item_id, user_id=current_user.id).first()
    if not w:
        return jsonify(error="未找到"), 404
    db.session.delete(w)
    db.session.commit()
    app_logger.info(f"用户 {current_user.username} 删除自选: {w.market}:{w.ticker}")
    return jsonify(status="deleted")


# ────────────────────────── API: 自选行情 ──────────────────────────

@app.route("/api/watchlist/quotes")
@login_required
def api_watchlist_quotes():
    """获取自选列表的实时行情"""
    items = Watchlist.query.filter_by(user_id=current_user.id).all()
    if not items:
        return jsonify([])

    from data.market_data import get_quotes_batch
    quote_input = [{"ticker": w.ticker, "market": w.market, "name": w.name} for w in items]
    quotes = get_quotes_batch(quote_input)

    # 用自选表的 name 补充（yfinance 可能缺中文名）
    name_map = {(w.ticker, w.market): w.name for w in items}
    id_map = {(w.ticker, w.market): w.id for w in items}
    for q in quotes:
        key = (q["ticker"], q["market"])
        if not q.get("name") and key in name_map:
            q["name"] = name_map[key]
        q["watchlist_id"] = id_map.get(key)

    return jsonify(quotes)


# ────────────────────────── API: 每日报告 ──────────────────────────

@app.route("/api/report")
@login_required
def api_report():
    """
    获取指定市场的每日报告：?market=a_share&date=2026-03-11
    不传 date 默认返回最新一期
    """
    market = request.args.get("market", "a_share")
    date_str = request.args.get("date", "")

    if date_str:
        try:
            target_date = date.fromisoformat(date_str)
        except ValueError:
            return jsonify(error="日期格式错误"), 400
        report = DailyReport.query.filter_by(market=market, report_date=target_date).first()
    else:
        report = DailyReport.query.filter_by(market=market).order_by(DailyReport.report_date.desc()).first()

    if not report:
        return jsonify(data=None, message="暂无报告")

    return jsonify(
        market=report.market,
        report_date=report.report_date.isoformat(),
        generated_at=report.generated_at.isoformat(),
        data=json.loads(report.data),
    )


# ────────────────────────── 启动入口 ──────────────────────────

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        _load_symbols()
    app_logger.info("Alpha Vault 启动")
    app.run(host="0.0.0.0", port=5000, debug=True)
