"""
core/dom_extractor.py — Lớp 1: Perception
==========================================
Nhiệm vụ duy nhất: biến trang hiện tại thành thứ LLM hiểu được.

Kỹ thuật Set-of-Mark:
  - Inject JS vào DOM để quét toàn bộ phần tử tương tác được và đang hiển thị.
  - Gắn data-agent-id ổn định lên từng phần tử.
  - Trả về:
      • text_snapshot  — tóm tắt dạng text (id, role, nội dung, trong/ngoài viewport)
      • screenshot_b64 — ảnh PNG base64 của viewport hiện tại
"""
import base64
import logging
from playwright.async_api import Page

logger = logging.getLogger(__name__)

# JS inject vào trang để tìm và gắn id lên các phần tử tương tác
_MARK_ELEMENTS_JS = """
() => {
    const INTERACTIVE_ROLES = new Set([
        'button','link','menuitem','tab','checkbox','radio',
        'textbox','combobox','listbox','option','switch','treeitem'
    ]);
    const INTERACTIVE_TAGS = new Set(['a','button','input','select','textarea','label']);
    const DATA_KEY = 'data-agent-id';

    function isVisible(el) {
        const r = el.getBoundingClientRect();
        if (r.width === 0 || r.height === 0) return false;
        const style = getComputedStyle(el);
        return style.display !== 'none'
            && style.visibility !== 'hidden'
            && style.opacity !== '0';
    }

    function isInteractive(el) {
        if (INTERACTIVE_TAGS.has(el.tagName.toLowerCase())) return true;
        const role = (el.getAttribute('role') || '').toLowerCase();
        if (INTERACTIVE_ROLES.has(role)) return true;
        const style = getComputedStyle(el);
        if (style.cursor === 'pointer') return true;
        return false;
    }

    function inViewport(el) {
        const r = el.getBoundingClientRect();
        return r.top < window.innerHeight && r.bottom > 0
            && r.left < window.innerWidth  && r.right > 0;
    }

    // Xoá id cũ từ lần chạy trước (nếu có) để gán lại sạch
    document.querySelectorAll('[data-agent-id]').forEach(el => el.removeAttribute(DATA_KEY));

    const elements = Array.from(document.querySelectorAll('*'))
        .filter(el => isInteractive(el) && isVisible(el));

    const result = [];
    elements.forEach((el, idx) => {
        const id = `a${idx}`;
        el.setAttribute(DATA_KEY, id);
        const r = el.getBoundingClientRect();
        result.push({
            id,
            tag:     el.tagName.toLowerCase(),
            role:    el.getAttribute('role') || el.tagName.toLowerCase(),
            text:    (el.innerText || el.getAttribute('aria-label') || el.getAttribute('placeholder') || '').trim().slice(0, 120),
            href:    el.getAttribute('href') || '',
            in_view: inViewport(el),
            x: Math.round(r.x + r.width / 2),
            y: Math.round(r.y + r.height / 2),
        });
    });
    return result;
}
"""


async def extract(page: Page) -> dict:
    """
    Quét trang, gắn data-agent-id, chụp screenshot.

    Trả về:
        {
            "text_snapshot": str,          # mô tả ngắn gọn để gửi cho LLM
            "elements": list[dict],        # raw data từng phần tử
            "screenshot_b64": str,         # PNG base64
        }
    """
    # 1. Inject JS và lấy danh sách phần tử
    try:
        elements: list[dict] = await page.evaluate(_MARK_ELEMENTS_JS)
    except Exception as e:
        logger.warning(f"[dom_extractor] Lỗi inject JS: {e}")
        elements = []

    # 2. Build text snapshot ngắn gọn cho LLM
    lines = [f"URL: {page.url}", f"Tổng phần tử tương tác: {len(elements)}", ""]
    in_view = [el for el in elements if el.get("in_view")]
    out_view = [el for el in elements if not el.get("in_view")]

    lines.append("=== TRONG VIEWPORT ===")
    for el in in_view:
        label = el["text"] or el["href"] or "(no label)"
        lines.append(f"  [{el['id']}] {el['role']} — {label}")

    if out_view:
        lines.append("\n=== NGOÀI VIEWPORT (cần scroll) ===")
        for el in out_view[:30]:  # giới hạn 30 để không phình token
            label = el["text"] or el["href"] or "(no label)"
            lines.append(f"  [{el['id']}] {el['role']} — {label}")
        if len(out_view) > 30:
            lines.append(f"  ... và {len(out_view) - 30} phần tử khác.")

    text_snapshot = "\n".join(lines)

    # 3. Chụp screenshot viewport
    try:
        screenshot_bytes = await page.screenshot(type="png", full_page=False)
        screenshot_b64 = base64.b64encode(screenshot_bytes).decode()
    except Exception as e:
        logger.warning(f"[dom_extractor] Không thể chụp screenshot: {e}")
        screenshot_b64 = ""

    return {
        "text_snapshot": text_snapshot,
        "elements": elements,
        "screenshot_b64": screenshot_b64,
    }
