"""
Account Summary Component - 계좌 현황 요약 컴포넌트
계좌별 잔고, 포트폴리오 가치, 손익 정보를 표시
"""

import streamlit as st
import pandas as pd
from typing import Dict, Any
from ...core import AutoTrader


def render_account_summary(auto_trader: AutoTrader) -> None:
    """계좌 현황 요약 렌더링"""
    st.subheader("📊 계좌 현황")
    
    try:
        portfolio_summary = auto_trader.get_portfolio_summary()
        _render_overall_summary(portfolio_summary)
        _render_accounts_detail(portfolio_summary)
        
    except Exception as e:
        st.error(f"계좌 정보 로드 실패: {e}")


def _render_overall_summary(summary: Dict[str, Any]) -> None:
    """전체 포트폴리오 요약 표시"""
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            "총 계좌", 
            summary.get('total_accounts', 0),
            delta=f"활성: {summary.get('active_accounts', 0)}"
        )
    
    with col2:
        total_value = summary.get('total_portfolio_value', 0)
        st.metric(
            "총 포트폴리오 가치",
            f"₩{total_value:,.0f}"
        )
    
    with col3:
        total_pnl = summary.get('total_unrealized_pnl', 0)
        pnl_color = "normal" if total_pnl >= 0 else "inverse"
        st.metric(
            "미실현 손익",
            f"₩{total_pnl:,.0f}",
            delta=f"{total_pnl:+.0f}",
            delta_color=pnl_color
        )


def _render_accounts_detail(summary: Dict[str, Any]) -> None:
    """계좌별 상세 정보 표시"""
    accounts_detail = summary.get('accounts_detail', {})
    
    if not accounts_detail:
        st.info("활성 계좌가 없습니다.")
        return
    
    # 계좌별 정보를 DataFrame으로 변환
    df_data = []
    for account_id, detail in accounts_detail.items():
        df_data.append({
            '계좌ID': account_id,
            '계좌명': detail.get('name', ''),
            '타입': detail.get('type', ''),
            '포트폴리오 가치': f"₩{detail.get('portfolio_value', 0):,.0f}",
            '미실현 손익': f"₩{detail.get('unrealized_pnl', 0):+,.0f}",
            '포지션 수': detail.get('positions_count', 0)
        })
    
    df = pd.DataFrame(df_data)
    st.dataframe(df, use_container_width=True, hide_index=True)


def render_balance_details(auto_trader: AutoTrader) -> None:
    """계좌별 잔고 상세 정보"""
    st.subheader("💰 계좌별 잔고")
    
    accounts = auto_trader.accounts
    
    for account_id, account in accounts.items():
        if not account.is_active:
            continue
            
        with st.expander(f"{account.name} ({account_id})"):
            try:
                balance = account.get_balance()
                
                col1, col2 = st.columns(2)
                with col1:
                    st.write(f"**총 잔고:** ₩{balance.get('total_balance', 0):,.0f}")
                    st.write(f"**통화:** {balance.get('currency', 'KRW')}")
                
                with col2:
                    st.write(f"**매수가능금액:** ₩{balance.get('available_balance', 0):,.0f}")
                    st.write(f"**계좌타입:** {account.account_type.value}")
                    
            except Exception as e:
                st.error(f"잔고 조회 실패: {e}")
