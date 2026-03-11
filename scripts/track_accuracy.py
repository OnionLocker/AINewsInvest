"""
scripts/track_accuracy.py - 推荐准确率追踪

每日运行，回填历史推荐的实际价格并判定盈亏。

逻辑：
  1. 查找所有 outcome='pending' 的推荐记录
  2. 根据推荐日期计算天数差
  3. 拉取当前价格，回填 price_after_Nd
  4. 检查是否触及止盈/止损，判定 outcome
  5. 超过 10 个交易日仍未触及的标记为 expired

用法：
  python scripts/track_accuracy.py           # 手动运行
  crontab: 0 18 * * 1-5 cd /path && python scripts/track_accuracy.py
"""
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def run():
    from app import app
    from models import db, RecommendationTrack
    from data.market_data import get_quote
    from utils.logger import app_logger

    with app.app_context():
        pending = RecommendationTrack.query.filter(
            RecommendationTrack.outcome.in_(["pending", None])
        ).all()

        if not pending:
            app_logger.info("[追踪] 无待追踪记录")
            return

        app_logger.info(f"[追踪] 开始处理 {len(pending)} 条待追踪记录")
        today = date.today()

        for track in pending:
            try:
                days_passed = (today - track.created_at.date()).days if track.created_at else 0
                if days_passed < 1:
                    continue

                quote = get_quote(track.ticker, track.market)
                if not quote or not quote.get("price"):
                    continue

                current_price = float(quote["price"])

                # 回填价格
                if days_passed >= 1 and not track.price_after_1d:
                    track.price_after_1d = current_price
                if days_passed >= 3 and not track.price_after_3d:
                    track.price_after_3d = current_price
                if days_passed >= 5 and not track.price_after_5d:
                    track.price_after_5d = current_price
                if days_passed >= 10 and not track.price_after_10d:
                    track.price_after_10d = current_price

                # 判定是否触及关键价位
                _check_hits(track, current_price)

                # 判定最终 outcome
                _determine_outcome(track, days_passed)

            except Exception as e:
                app_logger.warning(f"[追踪] {track.ticker} 处理失败: {e}")

        db.session.commit()
        settled = sum(1 for t in pending if t.outcome and t.outcome != "pending")
        app_logger.info(f"[追踪] 完成，已结算 {settled}/{len(pending)} 条")


def _check_hits(track, current_price: float):
    """检查当前价格是否触及止盈/止损"""
    if track.direction == "buy":
        if current_price >= track.take_profit_1 and not track.hit_tp1:
            track.hit_tp1 = True
        if current_price >= track.take_profit_2 and not track.hit_tp2:
            track.hit_tp2 = True
        if current_price <= track.stop_loss and not track.hit_sl:
            track.hit_sl = True
    else:  # sell
        if current_price <= track.take_profit_1 and not track.hit_tp1:
            track.hit_tp1 = True
        if current_price <= track.take_profit_2 and not track.hit_tp2:
            track.hit_tp2 = True
        if current_price >= track.stop_loss and not track.hit_sl:
            track.hit_sl = True


def _determine_outcome(track, days_passed: int):
    """根据触及情况判定最终结果"""
    if track.hit_sl and not track.hit_tp1:
        track.outcome = "loss"
    elif track.hit_tp2:
        track.outcome = "win"
    elif track.hit_tp1:
        if track.hit_sl:
            track.outcome = "partial"
        else:
            track.outcome = "win"
    elif days_passed >= 10:
        # 超过 10 天未触及任何目标，按盈亏判定
        ref_price = track.price_after_10d or track.price_after_5d
        if ref_price:
            if track.direction == "buy":
                track.outcome = "win" if ref_price > track.entry_price else "loss"
            else:
                track.outcome = "win" if ref_price < track.entry_price else "loss"
        else:
            track.outcome = "expired"


if __name__ == "__main__":
    run()
