import streamlit as st
from main_agent import AgentOrchestrator
import json

# Cấu hình giao diện trang
st.set_page_config(
    page_title="OSINT Facebook Orchestrator", page_icon="🕵️", layout="centered"
)

st.title("🕵️ Hệ Thống Điều Phối OSINT Facebook")
st.markdown(
    "Nhập yêu cầu bằng ngôn ngữ tự nhiên, hệ thống sẽ tự động phân tích và điều phối agent phía sau."
)

# Khởi tạo Orchestrator 1 lần duy nhất trong session state
if "orchestrator" not in st.session_state:
    st.session_state.orchestrator = AgentOrchestrator()

# Khởi tạo lịch sử tin nhắn
if "messages" not in st.session_state:
    st.session_state.messages = []

# Hiển thị lại các tin nhắn cũ từ lịch sử
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Nhận input từ người dùng
if prompt := st.chat_input(
    "Nhập yêu cầu thu thập dữ liệu (VD: Thu thập bài viết về VPBank)"
):
    # Thêm tin nhắn của user vào giao diện
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Xử lý kết quả từ Agent
    with st.chat_message("assistant"):
        with st.spinner("Đang phân tích ý định và thiết lập nhiệm vụ..."):
            try:
                # Orchestrator phân tích và đẩy vào Kafka
                result_urls, mission = st.session_state.orchestrator.execute(prompt)

                # Format kết quả hiển thị
                response_md = f"**Phân tích nhiệm vụ thành công!** ✅\n\n"
                response_md += f"- **Loại nhiệm vụ:** `{mission.mission_type}`\n"

                if mission.require_discovery:
                    response_md += f"- **Yêu cầu Discovery:** Có 🔍\n"
                    if result_urls:
                        response_md += f"- **Kết quả:** Đã tìm thấy **{len(result_urls)}** URLs mục tiêu và đẩy lô vào hàng đợi crawl!\n"
                    else:
                        response_md += (
                            f"- **Kết quả:** Không tìm thấy URL nào từ Discovery.\n"
                        )
                else:
                    response_md += f"- **Yêu cầu Discovery:** Không (Đã đẩy trực tiếp vào hàng đợi crawl 🚀)\n"

                # Hiển thị JSON config
                response_md += f"\n**Cấu hình Mission:**\n```json\n{mission.model_dump_json(indent=2)}\n```"

                st.markdown(response_md)
                st.session_state.messages.append(
                    {"role": "assistant", "content": response_md}
                )

            except Exception as e:
                error_msg = f"**Đã có lỗi xảy ra:** `{str(e)}`"
                st.error(error_msg)
                st.session_state.messages.append(
                    {"role": "assistant", "content": error_msg}
                )
