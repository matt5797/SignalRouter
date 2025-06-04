"""
Dashboard - Streamlit 기반 메인 대시보드
계좌 현황, 포지션, 거래 내역, 수동 주문, 비상 정지 기능 제공
"""

import streamlit as st
import time
from typing import Optional
from ..core import AutoTrader
from .components.account_summary import render_account_summary, render_balance_details
from .components.position_view import render_positions_overview, render_position_details
from .components.trade_history import render_trade_history


class Dashboard:
    """Streamlit 대시보드 메인 클래스"""
    
    def __init__(self, config_path: str = "config/config.yaml"):
        """대시보드 초기화"""
        self.auto_trader = AutoTrader(config_path)
        self._setup_page_config()
    
    def run(self) -> None:
        """대시보드 메인 실행"""
        self._render_header()
        
        # 사이드바 메뉴
        page = self._render_sidebar()
        
        # 메인 콘텐츠
        if page == "개요":
            self._render_overview_page()
        elif page == "포지션":
            self._render_positions_page()
        elif page == "거래내역":
            self._render_history_page()
        elif page == "수동거래":
            self._render_manual_trading_page()
        elif page == "설정":
            self._render_settings_page()
    
    def _setup_page_config(self) -> None:
        """페이지 설정"""
        st.set_page_config(
            page_title="SignalRouter Dashboard",
            page_icon="📊",
            layout="wide",
            initial_sidebar_state="expanded"
        )
    
    def _render_header(self) -> None:
        """헤더 렌더링"""
        col1, col2, col3 = st.columns([2, 1, 1])
        
        with col1:
            st.title("📊 SignalRouter Dashboard")
        
        with col2:
            if st.button("🔄 새로고침", use_container_width=True):
                st.rerun()
        
        with col3:
            self._render_emergency_stop_button()
        
        # 시스템 상태 표시
        self._render_system_status()
    
    def _render_sidebar(self) -> str:
        """사이드바 메뉴 렌더링"""
        with st.sidebar:
            st.header("메뉴")
            
            page = st.radio(
                "페이지 선택",
                ["개요", "포지션", "거래내역", "수동거래", "설정"],
                key="page_selection"
            )
            
            st.divider()
            
            # 빠른 통계
            self._render_quick_stats()
            
            return page
    
    def _render_overview_page(self) -> None:
        """개요 페이지 렌더링"""
        render_account_summary(self.auto_trader)
        st.divider()
        render_balance_details(self.auto_trader)
    
    def _render_positions_page(self) -> None:
        """포지션 페이지 렌더링"""
        render_positions_overview(self.auto_trader)
        st.divider()
        render_position_details(self.auto_trader)
    
    def _render_history_page(self) -> None:
        """거래내역 페이지 렌더링"""
        render_trade_history(self.auto_trader)
    
    def _render_manual_trading_page(self) -> None:
        """수동거래 페이지 렌더링"""
        st.subheader("🎯 수동 주문")
        
        col1, col2 = st.columns([1, 1])
        
        with col1:
            self._render_manual_order_panel()
        
        with col2:
            self._render_order_status_panel()
    
    def _render_settings_page(self) -> None:
        """설정 페이지 렌더링"""
        st.subheader("⚙️ 시스템 설정")
        
        # 계좌 관리
        self._render_account_management()
        
        st.divider()
        
        # 리스크 관리 설정
        self._render_risk_settings()
    
    def _render_emergency_stop_button(self) -> None:
        """비상 정지 버튼"""
        if self.auto_trader._emergency_stop:
            if st.button("🟢 거래재개", use_container_width=True, type="primary"):
                self.auto_trader.resume_trading()
                st.success("거래가 재개되었습니다.")
                time.sleep(1)
                st.rerun()
        else:
            if st.button("🛑 비상정지", use_container_width=True, type="secondary"):
                self.auto_trader.emergency_stop_all()
                st.error("비상 정지가 활성화되었습니다.")
                time.sleep(1)
                st.rerun()
    
    def _render_system_status(self) -> None:
        """시스템 상태 표시"""
        if self.auto_trader._emergency_stop:
            st.error("🛑 비상 정지 상태 - 모든 거래가 중단되었습니다.")
        else:
            st.success("🟢 시스템 정상 운영 중")
    
    def _render_quick_stats(self) -> None:
        """빠른 통계 표시"""
        try:
            summary = self.auto_trader.get_portfolio_summary()
            
            st.metric(
                "활성 계좌",
                summary.get('active_accounts', 0)
            )
            
            total_value = summary.get('total_portfolio_value', 0)
            st.metric(
                "포트폴리오",
                f"₩{total_value/1000000:.1f}M" if total_value >= 1000000 else f"₩{total_value:,.0f}"
            )
            
        except Exception as e:
            st.error(f"통계 로드 실패: {e}")
    
    def _render_manual_order_panel(self) -> None:
        """수동 주문 패널"""
        st.write("**새 주문**")
        
        # 계좌 선택
        active_accounts = {
            acc_id: acc.name for acc_id, acc in self.auto_trader.accounts.items() 
            if acc.is_active
        }
        
        if not active_accounts:
            st.warning("활성 계좌가 없습니다.")
            return
        
        selected_account = st.selectbox(
            "계좌",
            options=list(active_accounts.keys()),
            format_func=lambda x: f"{active_accounts[x]} ({x})",
            key="manual_order_account"
        )
        
        # 주문 정보 입력
        symbol = st.text_input("종목코드", placeholder="AAPL", key="manual_order_symbol")
        action = st.selectbox("주문유형", ["BUY", "SELL"], key="manual_order_action")
        quantity = st.number_input("수량", min_value=1, value=1, key="manual_order_quantity")
        price = st.number_input("가격 (0 = 시장가)", min_value=0.0, value=0.0, key="manual_order_price")
        
        if st.button("주문 실행", type="primary", use_container_width=True):
            self._execute_manual_order(selected_account, symbol, action, quantity, price)
    
    def _render_order_status_panel(self) -> None:
        """주문 상태 패널"""
        st.write("**최근 주문 현황**")
        
        try:
            # 최근 주문 5개 표시
            recent_trades = []
            for account_id in self.auto_trader.accounts.keys():
                trades = self.auto_trader.db.get_account_trades(account_id, limit=5)
                recent_trades.extend(trades)
            
            # 최신순 정렬
            recent_trades.sort(
                key=lambda x: x.get('signal_time', ''),
                reverse=True
            )
            
            for trade in recent_trades[:5]:
                status_color = "🟢" if trade.get('status') == 'FILLED' else "🔴" if trade.get('status') == 'FAILED' else "🟡"
                st.write(f"{status_color} {trade.get('symbol', '')} {trade.get('action', '')} {trade.get('quantity', 0)}")
                
        except Exception as e:
            st.error(f"주문 현황 로드 실패: {e}")
    
    def _execute_manual_order(self, account_id: str, symbol: str, action: str, quantity: int, price: float) -> None:
        """수동 주문 실행"""
        try:
            account = self.auto_trader.get_account(account_id)
            if not account:
                st.error("계좌를 찾을 수 없습니다.")
                return
            
            # 주문 데이터 구성
            order_data = {
                'symbol': symbol.upper(),
                'action': action,
                'quantity': quantity,
                'price': price if price > 0 else None
            }
            
            # 주문 실행
            order_id = self.auto_trader.trade_executor.place_order(account, order_data)
            st.success(f"주문이 실행되었습니다. 주문번호: {order_id}")
            
        except Exception as e:
            st.error(f"주문 실행 실패: {e}")
    
    def _render_account_management(self) -> None:
        """계좌 관리 섹션"""
        st.write("**계좌 관리**")
        
        for account_id, account in self.auto_trader.accounts.items():
            col1, col2, col3 = st.columns([2, 1, 1])
            
            with col1:
                st.write(f"{account.name} ({account_id})")
            
            with col2:
                status = "🟢 활성" if account.is_active else "🔴 비활성"
                st.write(status)
            
            with col3:
                if st.button(
                    "비활성화" if account.is_active else "활성화",
                    key=f"toggle_{account_id}",
                    use_container_width=True
                ):
                    account.is_active = not account.is_active
                    st.rerun()
    
    def _render_risk_settings(self) -> None:
        """리스크 관리 설정"""
        st.write("**리스크 관리**")
        
        col1, col2 = st.columns(2)
        
        with col1:
            max_position_ratio = st.slider(
                "최대 포지션 비율 (%)",
                min_value=10,
                max_value=100,
                value=30,
                step=5
            )
        
        with col2:
            max_daily_loss = st.number_input(
                "일일 최대 손실 (원)",
                min_value=100000,
                max_value=10000000,
                value=1000000,
                step=100000
            )
        
        if st.button("설정 저장"):
            st.info("설정이 저장되었습니다. (구현 예정)")


def main():
    """메인 함수"""
    dashboard = Dashboard()
    dashboard.run()


if __name__ == "__main__":
    main()
