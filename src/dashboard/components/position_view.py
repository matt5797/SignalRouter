"""
Position View Component - 포지션 모니터링 컴포넌트
현재 포지션 목록, 손익률, 시장가치를 표시
"""

import streamlit as st
import pandas as pd
from typing import Dict, List, Any
from ...core import AutoTrader


def render_positions_overview(auto_trader: AutoTrader) -> None:
    """포지션 현황 개요 렌더링"""
    st.subheader("📈 포지션 현황")
    
    try:
        all_positions = auto_trader.get_all_positions()
        _render_position_summary(all_positions)
        _render_positions_table(all_positions)
        
    except Exception as e:
        st.error(f"포지션 정보 로드 실패: {e}")


def _render_position_summary(all_positions: Dict[str, List]) -> None:
    """포지션 요약 통계"""
    total_positions = sum(len(positions) for positions in all_positions.values())
    long_positions = 0
    short_positions = 0
    
    # 롱/숏 포지션 계산
    for positions in all_positions.values():
        for pos in positions:
            if pos.get('quantity', 0) > 0:
                long_positions += 1
            elif pos.get('quantity', 0) < 0:
                short_positions += 1
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("총 포지션", total_positions)
    with col2:
        st.metric("롱 포지션", long_positions, delta="매수")
    with col3:
        st.metric("숏 포지션", short_positions, delta="매도")


def _render_positions_table(all_positions: Dict[str, List]) -> None:
    """포지션 테이블 표시"""
    if not any(all_positions.values()):
        st.info("현재 보유 중인 포지션이 없습니다.")
        return
    
    # 계좌 필터
    account_filter = st.selectbox(
        "계좌 선택",
        ["전체"] + list(all_positions.keys()),
        key="position_account_filter"
    )
    
    # 데이터 준비
    df_data = []
    for account_id, positions in all_positions.items():
        if account_filter != "전체" and account_id != account_filter:
            continue
            
        for pos in positions:
            df_data.append({
                '계좌': account_id,
                '종목': pos.get('symbol', ''),
                '수량': pos.get('quantity', 0),
                '평균단가': f"₩{pos.get('avg_price', 0):,.0f}",
                '현재가치': f"₩{pos.get('current_value', 0):,.0f}",
                '미실현손익': f"₩{pos.get('unrealized_pnl', 0):+,.0f}",
                '방향': _get_position_direction(pos.get('quantity', 0))
            })
    
    if df_data:
        df = pd.DataFrame(df_data)
        st.dataframe(
            df, 
            use_container_width=True,
            hide_index=True,
            column_config={
                '미실현손익': st.column_config.TextColumn(
                    help="미실현 손익 (+ 이익, - 손실)"
                )
            }
        )
    else:
        st.info("선택한 계좌에 포지션이 없습니다.")


def _get_position_direction(quantity: int) -> str:
    """포지션 방향 반환"""
    if quantity > 0:
        return "🟢 롱"
    elif quantity < 0:
        return "🔴 숏"
    else:
        return "⚪ 플랫"


def render_position_details(auto_trader: AutoTrader) -> None:
    """포지션 상세 정보"""
    st.subheader("🔍 포지션 상세")
    
    # 계좌 선택
    account_options = {acc_id: acc.name for acc_id, acc in auto_trader.accounts.items() if acc.is_active}
    
    if not account_options:
        st.warning("활성 계좌가 없습니다.")
        return
    
    selected_account = st.selectbox(
        "계좌 선택",
        options=list(account_options.keys()),
        format_func=lambda x: f"{account_options[x]} ({x})",
        key="position_detail_account"
    )
    
    if selected_account:
        account = auto_trader.get_account(selected_account)
        if account:
            try:
                positions = account.get_positions()
                
                if positions:
                    # 종목 선택
                    symbols = [pos['symbol'] for pos in positions]
                    selected_symbol = st.selectbox("종목 선택", symbols, key="position_detail_symbol")
                    
                    if selected_symbol:
                        position = next(pos for pos in positions if pos['symbol'] == selected_symbol)
                        _render_single_position_detail(position)
                else:
                    st.info("해당 계좌에 포지션이 없습니다.")
                    
            except Exception as e:
                st.error(f"포지션 상세 조회 실패: {e}")


def _render_single_position_detail(position: Dict[str, Any]) -> None:
    """단일 포지션 상세 정보 표시"""
    col1, col2 = st.columns(2)
    
    with col1:
        st.write("**기본 정보**")
        st.write(f"종목: {position.get('symbol', '')}")
        st.write(f"수량: {position.get('quantity', 0):,}주")
        st.write(f"평균단가: ₩{position.get('avg_price', 0):,.0f}")
        
    with col2:
        st.write("**손익 정보**")
        st.write(f"현재가치: ₩{position.get('current_value', 0):,.0f}")
        st.write(f"미실현손익: ₩{position.get('unrealized_pnl', 0):+,.0f}")
        
        # 간단한 손익률 계산 (현재가가 있다면)
        quantity = position.get('quantity', 0)
        avg_price = position.get('avg_price', 0)
        if quantity != 0 and avg_price > 0:
            invested_amount = abs(quantity) * avg_price
            if invested_amount > 0:
                pnl_rate = (position.get('unrealized_pnl', 0) / invested_amount) * 100
                st.write(f"손익률: {pnl_rate:+.2f}%")
