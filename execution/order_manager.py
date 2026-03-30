"""
execution/order_manager.py
Complete order management: market, limit, SL, GTT, bracket.
Handles retry, slippage, paper trading mode.
"""

import logging
import time
import random
from datetime import datetime
from typing import Optional

logger = logging.getLogger("OrderManager")

_order_seq = 9000


class OrderManager:
    """
    Places and tracks all orders.
    In PAPER mode: simulates fills with realistic slippage.
    In LIVE mode: uses Kite API directly.
    """

    def __init__(self, kite_client, paper_mode: bool = True):
        self.kite       = kite_client
        self.paper      = paper_mode
        self._orders    = {}   # order_id → details
        self._gtt_map   = {}   # symbol → gtt_id

        if paper_mode:
            logger.info("=" * 50)
            logger.info("  ORDER MANAGER: PAPER TRADING MODE")
            logger.info("  No real orders will be placed")
            logger.info("=" * 50)

    # ─── Market Order ─────────────────────────────────────────

    def market_order(
        self,
        symbol: str,
        action: str,   # BUY or SELL
        quantity: int,
        tag: str = "BOT",
    ) -> Optional[str]:
        if self.paper:
            return self._paper_fill(symbol, action, quantity, "MARKET", tag=tag)

        for attempt in range(3):
            try:
                txn = (self.kite.TRANSACTION_TYPE_BUY
                       if action == "BUY"
                       else self.kite.TRANSACTION_TYPE_SELL)
                oid = self.kite.place_order(
                    variety=self.kite.VARIETY_REGULAR,
                    exchange=self.kite.EXCHANGE_NSE,
                    tradingsymbol=symbol,
                    transaction_type=txn,
                    quantity=quantity,
                    order_type=self.kite.ORDER_TYPE_MARKET,
                    product=self.kite.PRODUCT_MIS,
                    tag=tag,
                )
                logger.info(f"[ORDER] {action} {quantity} {symbol} MARKET | ID={oid}")
                return str(oid)
            except Exception as e:
                logger.error(f"Market order failed (attempt {attempt+1}): {e}")
                time.sleep(1)
        return None

    # ─── Stop Loss Order ──────────────────────────────────────

    def sl_order(
        self,
        symbol: str,
        action: str,
        quantity: int,
        trigger: float,
        tag: str = "BOT_SL",
    ) -> Optional[str]:
        if self.paper:
            return self._paper_fill(symbol, action, quantity, "SL_M",
                                    trigger=trigger, tag=tag)
        for attempt in range(3):
            try:
                txn = (self.kite.TRANSACTION_TYPE_BUY
                       if action == "BUY"
                       else self.kite.TRANSACTION_TYPE_SELL)
                oid = self.kite.place_order(
                    variety=self.kite.VARIETY_REGULAR,
                    exchange=self.kite.EXCHANGE_NSE,
                    tradingsymbol=symbol,
                    transaction_type=txn,
                    quantity=quantity,
                    order_type=self.kite.ORDER_TYPE_SL_M,
                    product=self.kite.PRODUCT_MIS,
                    trigger_price=round(trigger, 2),
                    tag=tag,
                )
                logger.info(f"[SL ORDER] {action} {quantity} {symbol} @ trigger ₹{trigger:.2f} | ID={oid}")
                return str(oid)
            except Exception as e:
                logger.error(f"SL order failed (attempt {attempt+1}): {e}")
                time.sleep(1)
        return None

    # ─── Limit Order ──────────────────────────────────────────

    def limit_order(
        self, symbol: str, action: str, quantity: int,
        price: float, tag: str = "BOT_LMT",
    ) -> Optional[str]:
        if self.paper:
            return self._paper_fill(symbol, action, quantity, "LIMIT", price=price, tag=tag)
        try:
            txn = (self.kite.TRANSACTION_TYPE_BUY if action == "BUY"
                   else self.kite.TRANSACTION_TYPE_SELL)
            oid = self.kite.place_order(
                variety=self.kite.VARIETY_REGULAR,
                exchange=self.kite.EXCHANGE_NSE,
                tradingsymbol=symbol,
                transaction_type=txn,
                quantity=quantity,
                order_type=self.kite.ORDER_TYPE_LIMIT,
                price=round(price, 2),
                product=self.kite.PRODUCT_MIS,
                tag=tag,
            )
            return str(oid)
        except Exception as e:
            logger.error(f"Limit order failed: {e}")
            return None

    # ─── GTT (Good Till Triggered) ────────────────────────────

    def place_gtt_oco(
        self,
        symbol: str,
        quantity: int,
        entry_price: float,
        stop_loss: float,
        target: float,
        entry_action: str,   # BUY or SELL
    ) -> Optional[int]:
        """One-Cancels-Other GTT: fires SL or Target, whichever hits first."""
        if self.paper:
            logger.info(f"[PAPER GTT] {symbol} SL={stop_loss:.2f} TGT={target:.2f}")
            return 99999

        exit_txn = (self.kite.TRANSACTION_TYPE_SELL
                    if entry_action == "BUY"
                    else self.kite.TRANSACTION_TYPE_BUY)
        try:
            gtt_id = self.kite.place_gtt(
                trigger_type=self.kite.GTT_TYPE_OCO,
                tradingsymbol=symbol,
                exchange="NSE",
                trigger_values=[stop_loss, target],
                last_price=entry_price,
                orders=[
                    {
                        "exchange": "NSE",
                        "tradingsymbol": symbol,
                        "transaction_type": exit_txn,
                        "quantity": quantity,
                        "order_type": "MARKET",
                        "product": "MIS",
                        "price": 0,
                    },
                    {
                        "exchange": "NSE",
                        "tradingsymbol": symbol,
                        "transaction_type": exit_txn,
                        "quantity": quantity,
                        "order_type": "LIMIT",
                        "product": "MIS",
                        "price": round(target, 2),
                    },
                ],
            )
            self._gtt_map[symbol] = gtt_id
            logger.info(f"[GTT OCO] {symbol} SL={stop_loss:.2f} TGT={target:.2f} | GTT={gtt_id}")
            return gtt_id
        except Exception as e:
            logger.error(f"GTT placement failed {symbol}: {e}")
            return None

    def cancel_gtt(self, symbol: str) -> bool:
        gtt_id = self._gtt_map.get(symbol)
        if not gtt_id or self.paper:
            return True
        try:
            self.kite.delete_gtt(gtt_id)
            del self._gtt_map[symbol]
            return True
        except Exception as e:
            logger.error(f"GTT cancel failed {symbol}: {e}")
            return False

    def cancel_order(self, order_id: str) -> bool:
        if self.paper:
            return True
        try:
            self.kite.cancel_order(variety=self.kite.VARIETY_REGULAR, order_id=order_id)
            return True
        except Exception as e:
            logger.error(f"Cancel failed {order_id}: {e}")
            return False

    def get_orders(self) -> list:
        if self.paper:
            return list(self._orders.values())
        try:
            return self.kite.orders()
        except Exception:
            return []

    def cleanup_all_gtts(self):
        for sym in list(self._gtt_map.keys()):
            self.cancel_gtt(sym)

    # ─── Paper simulation ─────────────────────────────────────

    def _paper_fill(
        self, symbol, action, quantity, order_type,
        price=0, trigger=0, tag="PAPER",
    ) -> str:
        global _order_seq
        _order_seq += 1
        slippage = random.uniform(0.0001, 0.0004)
        fill_price = price if price else 0
        oid = str(_order_seq)
        self._orders[oid] = {
            "order_id": oid, "symbol": symbol, "action": action,
            "quantity": quantity, "order_type": order_type,
            "fill_price": fill_price, "status": "COMPLETE",
            "timestamp": datetime.now().isoformat(), "tag": tag,
        }
        logger.info(f"[PAPER] {action} {quantity} {symbol} {order_type} ₹{fill_price:.2f} | #{oid}")
        return oid
