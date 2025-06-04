"""
Trade History Component - 거래 내역 조회 컴포넌트
최근 거래 내역, 필터링, 상태별 조회 기능 제공
"""

import streamlit as st
import pandas as pd
from typing import Dict, List, Any
from datetime import datetime, date, timedelta
from ...core import AutoTrader


def render_trade_history(auto_trader: AutoTrader) -> None:
    """거래 내역 렌더링"""
    st.subheader("📋 거래 내역")
    
    try:
        # 필터 옵션
        filters = _render_trade_filters(auto_trader)
        
        # 거래 내역 조회 및 표시
        _render_trades_table(auto_trader, filters)
        
    except Exception as e:
        st.error(f"거래 내역 로드 실패: {e}")


def _render_trade_filters(auto_trader: AutoTrader) -> Dict[str, Any]:
    """거래 내역 필터 렌더링"""
    col1, col2, col3 = st.columns(3)
    
    with col1:
        # 계좌 필터
        account_options = ["전체"] + [
            acc_id for acc_id, acc in auto_trader.accounts.items() if acc.is_active
        ]
        selected_account = st.selectbox("계좌", account_options, key="trade_account_filter")
    
    with col2:
        # 거래 상태 필터
        status_options = ["전체", "SIGNAL", "PENDING", "FILLED", "FAILED"]
        selected_status = st.selectbox("상태", status_options, key="trade_status_filter")
    
    with col3:
        # 조회 기간
        period_options = ["오늘", "최근 3일", "최근 7일", "최근 30일", "전체"]
        selected_period = st.selectbox("기간", period_options, key="trade_period_filter")
    
    return {
        'account': selected_account,
        'status': selected_status,
        'period': selected_period
    }


def _render_trades_table(auto_trader: AutoTrader, filters: Dict[str, Any]) -> None:
    """거래 내역 테이블 표시"""
    try:
        # 계좌별 거래 내역 조회
        all_trades = []
        
        if filters['account'] == "전체":
            for account_id in auto_trader.accounts.keys():
                trades = auto_trader.db.get_account_trades(account_id, limit=200)
                all_trades.extend(trades)
        else:
            trades = auto_trader.db.get_account_trades(filters['account'], limit=200)
            all_trades.extend(trades)
        
        # 필터 적용
        filtered_trades = _apply_filters(all_trades, filters)
        
        if not filtered_trades:
            st.info("조건에 맞는 거래 내역이 없습니다.")
            return
        
        # 거래 요약 표시
        _render_trade_summary(filtered_trades)
        
        # 테이블 데이터 준비
        df_data = []
        for trade in filtered_trades:
            df_data.append({
                '시간': _format_datetime(trade.get('signal_time')),
                '계좌': trade.get('account_id', ''),
                '종목': trade.get('symbol', ''),
                '액션': _format_action(trade.get('action', '')),
                '수량': f"{trade.get('quantity', 0):,}",
                '가격': f"₩{trade.get('price', 0):,.0f}" if trade.get('price') else "시장가",
                '상태': _format_status(trade.get('status', '')),
                '전환타입': trade.get('transition_type', ''),
                '체결수량': f"{trade.get('filled_quantity', 0):,}",
                '체결가': f"₩{trade.get('avg_fill_price', 0):,.0f}" if trade.get('avg_fill_price') else "-"
            })
        
        df = pd.DataFrame(df_data)
        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            column_config={
                '시간': st.column_config.TextColumn(width="medium"),
                '상태': st.column_config.TextColumn(width="small")
            }
        )
        
    except Exception as e:
        st.error(f"거래 내역 조회 실패: {e}")


def _apply_filters(trades: List[Dict], filters: Dict[str, Any]) -> List[Dict]:
    """필터 조건 적용"""
    filtered = trades
    
    # 상태 필터
    if filters['status'] != "전체":
        filtered = [t for t in filtered if t.get('status') == filters['status']]
    
    # 기간 필터
    if filters['period'] != "전체":
        cutoff_date = _get_cutoff_date(filters['period'])
        filtered = [
            t for t in filtered 
            if t.get('signal_time') and 
            datetime.fromisoformat(t['signal_time'].replace('Z', '+00:00')) >= cutoff_date
        ]
    
    # 최신순 정렬
    filtered.sort(
        key=lambda x: datetime.fromisoformat(x['signal_time'].replace('Z', '+00:00')) if x.get('signal_time') else datetime.min,
        reverse=True
    )
    
    return filtered[:100]  # 최대 100개만 표시


def _get_cutoff_date(period: str) -> datetime:
    """기간별 컷오프 날짜 계산"""
    now = datetime.now()
    
    if period == "오늘":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "최근 3일":
        return now - timedelta(days=3)
    elif period == "최근 7일":
        return now - timedelta(days=7)
    elif period == "최근 30일":
        return now - timedelta(days=30)
    else:
        return datetime.min


def _render_trade_summary(trades: List[Dict]) -> None:
    """거래 요약 통계"""
    total_trades = len(trades)
    filled_trades = len([t for t in trades if t.get('status') == 'FILLED'])
    failed_trades = len([t for t in trades if t.get('status') == 'FAILED'])
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("총 거래", total_trades)
    with col2:
        st.metric("체결", filled_trades)
    with col3:
        st.metric("실패", failed_trades)
    with col4:
        success_rate = (filled_trades / total_trades * 100) if total_trades > 0 else 0
        st.metric("체결률", f"{success_rate:.1f}%")


def _format_datetime(dt_str: str) -> str:
    """날짜시간 포맷팅"""
    if not dt_str:
        return "-"
    try:
        dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
        return dt.strftime("%m/%d %H:%M")
    except:
        return dt_str


def _format_action(action: str) -> str:
    """액션 포맷팅"""
    if action == "BUY":
        return "🟢 매수"
    elif action == "SELL":
        return "🔴 매도"
    return action


def _format_status(status: str) -> str:
    """상태 포맷팅"""
    status_map = {
        'SIGNAL': '📡 시그널',
        'PENDING': '⏳ 대기',
        'FILLED': '✅ 체결',
        'FAILED': '❌ 실패'
    }
    return status_map.get(status, status)
