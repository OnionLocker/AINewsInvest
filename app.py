"""
app.py - AI 投研系统 Flask 主应用

架构借鉴 QuantProject：
  - 日志系统（utils/logger）贯穿全局
  - 工厂模式通知器（utils/notifier）
  - Fernet 加密存储敏感数据（utils/crypto）
  - config.yaml 热重载（utils/config_loader）
  - .env 管理密钥（与业务配置分离）
  - /api/health 健康检查端点
"""
from datetime import datetime
from flask import Flask, render_template, redirect, url_for, request, flash, jsonify
from flask_login import (
    LoginManager,
    login_user,
    logout_user,
    login_required,
    current_user,
)
from config import Config
from models import db, User
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


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# ────────────────────────── 健康检查 ──────────────────────────


@app.route("/api/health")
def health():
    """供 Nginx / 监控系统探活"""
    return jsonify(status="ok", time=datetime.now().isoformat())


# ────────────────────────── 注册 ──────────────────────────


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


# ────────────────────────── 登录 ──────────────────────────


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
            next_page = request.args.get("next")
            return redirect(next_page or url_for("dashboard"))

        app_logger.warning(f"登录失败: {username}")
        flash("用户名或密码错误", "danger")
        return redirect(url_for("login"))

    return render_template("login.html")


# ────────────────────────── 退出 ──────────────────────────


@app.route("/logout")
@login_required
def logout():
    app_logger.info(f"用户退出: {current_user.username}")
    logout_user()
    flash("已安全退出登录", "info")
    return redirect(url_for("login"))


# ────────────────────────── 仪表盘 ──────────────────────────


@app.route("/")
@login_required
def dashboard():
    return render_template("dashboard.html")


# ────────────────────────── 推送设置 ──────────────────────────


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

    # GET: 解密回显（脱敏显示）
    token_display, chat_id_display = "", ""
    if current_user.tg_configured:
        try:
            t, c = current_user.get_tg_config()
            token_display = t[:10] + "****" + t[-4:] if len(t) > 14 else "******"
            chat_id_display = c
        except Exception:
            token_display = "(解密失败，请重新保存)"

    return render_template(
        "settings.html",
        token_display=token_display,
        chat_id_display=chat_id_display,
    )


# ────────────────────────── 启动入口 ──────────────────────────

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app_logger.info("AI 投研系统启动")
    app.run(host="0.0.0.0", port=5000, debug=True)
