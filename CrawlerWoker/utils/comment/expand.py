"""
expand_prune.py
---------------
Bung nút 'Xem thêm', click expand comment/reply,
và prune các comment article đã xử lý để tránh DOM phình.
"""

import time
import os
import re
from typing import List, Optional, Set

from src.driver.browser_compat import (
    By,
    EC,
    ElementClickInterceptedException,
    ElementNotInteractableException,
    JavascriptException,
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
    WebDriverWait,
)
from src.driver.playwright_adapter import PlaywrightElementAdapter

# TODO_VERIFY_PLAYWRIGHT_EQUIVALENCE: Playwright locators usually re-resolve
# instead of raising stale-element errors; keep catches for browser parity.
from logs.loging_config import logger
from src.utils.selector_elements import safe_find_elements
from src.comment.scroll import find_comment_scroll_target
from src.facebook.facebook_text import extract_comment_ids_from_href, fold_text, normalize_text


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EXPAND_PATTERNS = [
    "xem thêm", "xem thêm bình luận", "xem thêm câu trả lời",
    "xem thêm phản hồi", "xem tất cả phản hồi",
    "phản hồi trước", "bình luận trước",
]

SKIP_PATTERNS = [
    "ẩn bớt", "thích", "chia sẻ", "gửi", "viết bình luận",
    "bày tỏ cảm xúc", "tất cả cảm xúc", "hành động với bài viết này",
]

EXPAND_FOLD_PATTERNS = [
    "xem them",
    "xem them binh luan",
    "xem them cau tra loi",
    "xem them phan hoi",
    "xem tat ca phan hoi",
    "phan hoi truoc",
    "binh luan truoc",
    "view more",
    "see more",
    "view reply",
    "view replies",
    "previous replies",
    "previous comments",
]

SKIP_FOLD_PATTERNS = [
    "an bot",
    "thich",
    "chia se",
    "gui",
    "viet binh luan",
    "xem ai da bay to cam xuc",
    "bay to cam xuc",
    "tat ca cam xuc",
    "hanh dong voi bai viet nay",
    "all reactions",
    "reaction",
    "like",
    "share",
]

POST_SEE_MORE_PATTERNS = ["xem thêm", "see more"]

COMMENT_SORT_DROPDOWN_PATTERNS = ["phù hợp nhất", "most relevant", "top comments", "relevant"]
ALL_COMMENTS_PATTERNS = ["tất cả bình luận", "all comments"]

KEEP_ANCHORS = 250
PRUNE_BUFFER = 150
EXPAND_VIEWPORT_MARGIN_PX = 1200
EXPAND_MAX_CLICKS_PER_ROUND = 30
PRUNE_MAX_ARTICLES_PER_ROUND = 200


# ---------------------------------------------------------------------------
# Element state helpers
# ---------------------------------------------------------------------------

def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default


def _playwright_arg(value):
    to_handle = getattr(value, "_js_handle", None)
    if callable(to_handle):
        try:
            return to_handle()
        except Exception:
            return value
    return value


def _eval_js(driver, script: str, *args):
    page = getattr(driver, "_page", None)
    if page is not None and hasattr(page, "evaluate"):
        js_args = [_playwright_arg(arg) for arg in args]
        return page.evaluate(
            """
            ([source, ...args]) => {
              const fn = new Function(`return (function(){${source}\\n}).apply(window, arguments);`);
              return fn(...args);
            }
            """,
            [str(script or ""), *js_args],
        )
    return driver.execute_script(script, *args)


def element_visible_enabled(el) -> bool:
    try:
        return el.is_displayed() and el.is_enabled()
    except Exception:
        return False


def _is_reaction_viewer_trigger(driver, el) -> bool:
    if isinstance(el, PlaywrightElementAdapter):
        try:
            return bool(
                el._locator.evaluate(
                    """
                    el => {
                      if (!el) return false;
                      const fold = value => String(value || "")
                        .toLowerCase()
                        .normalize("NFD")
                        .replace(/[\\u0300-\\u036f]/g, "")
                        .replace(/\\u0111/g, "d")
                        .replace(/[\\u00a0\\u200b\\u200c\\u200d]+/g, " ")
                        .replace(/\\s+/g, " ")
                        .trim();
                      const reactionText = text => {
                        const t = fold(text);
                        if (!t) return false;
                        if (t.includes("xem ai da bay to cam xuc") || t.includes("bay to cam xuc") || t.includes("tat ca cam xuc")) return true;
                        if (t.includes("all reactions") || t.includes("reaction") || t.includes("reactions")) return true;
                        if (/^(thich|like|love|haha|wow|buon|sad|angry|phan no|care|yeu thich|thuong thuong)(:|\\s|$)/.test(t)) {
                          return /\\d/.test(t) || t.includes("nguoi") || t.includes("people");
                        }
                        return false;
                      };
                      const toolbar = el.closest && el.closest("[role='toolbar'][aria-label]");
                      if (toolbar && reactionText(toolbar.getAttribute("aria-label"))) return true;
                      let node = el;
                      for (let i = 0; node && i < 6; i += 1, node = node.parentElement) {
                        const role = node.getAttribute && node.getAttribute("role");
                        const label = [
                          node.getAttribute && node.getAttribute("aria-label"),
                          node.getAttribute && node.getAttribute("title"),
                          node.innerText || node.textContent
                        ].filter(Boolean).join(" ");
                        if ((role === "button" || role === "toolbar") && reactionText(label)) return true;
                      }
                      return false;
                    }
                    """
                )
            )
        except Exception:
            return False
    try:
        return bool(
            driver.execute_script(
                """
                const el = arguments[0];
                if (!el) return false;
                const fold = value => String(value || "")
                  .toLowerCase()
                  .normalize("NFD")
                  .replace(/[\\u0300-\\u036f]/g, "")
                  .replace(/\\u0111/g, "d")
                  .replace(/[\\u00a0\\u200b\\u200c\\u200d]+/g, " ")
                  .replace(/\\s+/g, " ")
                  .trim();
                const reactionText = text => {
                  const t = fold(text);
                  if (!t) return false;
                  if (t.includes("xem ai da bay to cam xuc") || t.includes("bay to cam xuc") || t.includes("tat ca cam xuc")) return true;
                  if (t.includes("all reactions") || t.includes("reaction") || t.includes("reactions")) return true;
                  if (/^(thich|like|love|haha|wow|buon|sad|angry|phan no|care|yeu thich|thuong thuong)(:|\\s|$)/.test(t)) {
                    return /\\d/.test(t) || t.includes("nguoi") || t.includes("people");
                  }
                  return false;
                };
                const toolbar = el.closest && el.closest("[role='toolbar'][aria-label]");
                if (toolbar && reactionText(toolbar.getAttribute("aria-label"))) return true;
                let node = el;
                for (let i = 0; node && i < 6; i += 1, node = node.parentElement) {
                  const role = node.getAttribute && node.getAttribute("role");
                  const label = [
                    node.getAttribute && node.getAttribute("aria-label"),
                    node.getAttribute && node.getAttribute("title"),
                    node.innerText || node.textContent
                  ].filter(Boolean).join(" ");
                  if ((role === "button" || role === "toolbar") && reactionText(label)) return true;
                }
                return false;
                """,
                el,
            )
        )
    except Exception:
        return False


def _safe_click_playwright(el) -> bool:
    if not isinstance(el, PlaywrightElementAdapter):
        return False
    try:
        clicked = el._locator.evaluate(
            """
            (el, args) => {
              if (!el) return false;
              const topPad = Math.max(0, Number(args.topPad || 96));
              const bottomPad = Math.max(0, Number(args.bottomPad || 160));
              const hasRealHref = node => {
                const href = String(node && node.getAttribute && node.getAttribute("href") || "").trim().toLowerCase();
                return href && !href.startsWith("#") && !href.startsWith("javascript:");
              };
              const fold = value => String(value || "")
                .toLowerCase()
                .normalize("NFD")
                .replace(/[\\u0300-\\u036f]/g, "")
                .replace(/đ/g, "d")
                .replace(/\\s+/g, " ")
                .trim();
              const reactionText = text => {
                const t = fold(text);
                if (!t) return false;
                if (t.includes("xem ai da bay to cam xuc") || t.includes("bay to cam xuc") || t.includes("tat ca cam xuc")) return true;
                if (t.includes("all reactions") || t.includes("reaction") || t.includes("reactions")) return true;
                if (/^(thich|like|love|haha|wow|buon|sad|angry|phan no|care|yeu thich|thuong thuong)(:|\\s|$)/.test(t)) {
                  return /\\d/.test(t) || t.includes("nguoi") || t.includes("people");
                }
                return false;
              };
              const looksLikeReplySummary = node => {
                if (!node || hasRealHref(node) || node.closest("a[href]")) return false;
                const text = fold(node.innerText || node.textContent || "");
                if (!text || text.length > 220) return false;
                if (text.includes("phan hoi") && (text.includes("da tra loi") || /\\b\\d+\\s+phan hoi\\b/.test(text))) return true;
                if ((text.includes("tra loi") || text.includes("cau tra loi")) && /\\b\\d+\\s+(?:tra loi|cau tra loi)\\b/.test(text)) return true;
                if (text.includes("repl") && (text.includes("replied") || text.includes("view") || text.includes("see") || text.includes("previous") || /\\b\\d+\\s+repl(?:y|ies)\\b/.test(text))) return true;
                return false;
              };
              let target = null;
              const button = el.closest("[role='button']");
              if (button && !hasRealHref(button) && !button.closest("a[href]")) target = button;
              const tab = !target && el.closest("[tabindex]:not([tabindex='-1'])");
              if (tab && !hasRealHref(tab) && !tab.closest("a[href]")) target = tab;
              for (let current = el, i = 0; !target && current && i < 7; i += 1, current = current.parentElement) {
                if (looksLikeReplySummary(current)) target = current;
              }
              if (!target && !hasRealHref(el) && !el.closest("a[href]")) target = el;
              if (!target) return false;

              const toolbar = target.closest && target.closest("[role='toolbar'][aria-label]");
              if (toolbar && reactionText(toolbar.getAttribute("aria-label"))) return false;
              for (let node = target, i = 0; node && i < 6; i += 1, node = node.parentElement) {
                const role = node.getAttribute && node.getAttribute("role");
                const label = [
                  node.getAttribute && node.getAttribute("aria-label"),
                  node.getAttribute && node.getAttribute("title"),
                  node.innerText || node.textContent
                ].filter(Boolean).join(" ");
                if ((role === "button" || role === "toolbar") && reactionText(label)) return false;
              }

              const scrollableAncestor = node => {
                for (let cur = node && node.parentElement; cur && cur !== document.body; cur = cur.parentElement) {
                  const style = window.getComputedStyle(cur);
                  const oy = String(style && style.overflowY || "").toLowerCase();
                  if ((oy === "auto" || oy === "scroll" || oy === "overlay") && cur.scrollHeight - cur.clientHeight > 40) {
                    return cur;
                  }
                }
                return null;
              };
              const revealInside = (viewTop, viewBottom, applyDelta) => {
                const rect = target.getBoundingClientRect();
                if (!rect || rect.width <= 0 || rect.height <= 0) return;
                let delta = 0;
                if (rect.top < viewTop + topPad) delta = rect.top - (viewTop + topPad);
                else if (rect.bottom > viewBottom - bottomPad) delta = rect.bottom - (viewBottom - bottomPad);
                if (Math.abs(delta) > 2) applyDelta(delta);
              };

              const scroller = scrollableAncestor(target);
              if (scroller) {
                const sr = scroller.getBoundingClientRect();
                revealInside(sr.top, sr.bottom, delta => {
                  const maxTop = Math.max(0, scroller.scrollHeight - scroller.clientHeight);
                  scroller.scrollTop = Math.max(0, Math.min(maxTop, scroller.scrollTop + delta));
                });
              } else {
                revealInside(0, window.innerHeight || document.documentElement.clientHeight || 0, delta => {
                  window.scrollBy({top: delta, left: 0, behavior: "instant"});
                });
              }

              try {
                const rect = target.getBoundingClientRect();
                const opts = {
                  bubbles: true,
                  cancelable: true,
                  view: window,
                  clientX: rect.left + rect.width / 2,
                  clientY: rect.top + rect.height / 2
                };
                for (const type of ["pointerdown", "mousedown", "pointerup", "mouseup", "click"]) {
                  target.dispatchEvent(new MouseEvent(type, opts));
                }
              } catch (e) {}
              try {
                if (typeof target.click === "function") target.click();
              } catch (e) {}
              return true;
            }
            """,
            {
                "topPad": _env_int("COMMENTS_EXPAND_SAFE_CLICK_TOP_PAD", 96),
                "bottomPad": _env_int("COMMENTS_EXPAND_SAFE_CLICK_BOTTOM_PAD", 160),
            },
        )
        if clicked:
            try:
                scroll_sleep = float(os.environ.get("COMMENTS_EXPAND_SAFE_CLICK_SCROLL_SLEEP", "0.006"))
            except (TypeError, ValueError):
                scroll_sleep = 0.006
            time.sleep(max(0.0, scroll_sleep))
        return bool(clicked)
    except Exception:
        return False


def safe_click(driver, el) -> bool:
    if isinstance(el, PlaywrightElementAdapter):
        return _safe_click_playwright(el)

    try:
        target = driver.execute_script(
            """
            const el = arguments[0];
            if (!el) return el;
            const hasRealHref = node => {
              const href = String(node && node.getAttribute && node.getAttribute("href") || "").trim().toLowerCase();
              return href && !href.startsWith("#") && !href.startsWith("javascript:");
            };
            const fold = value => String(value || "")
              .toLowerCase()
              .normalize("NFD")
              .replace(/[\\u0300-\\u036f]/g, "")
              .replace(/đ/g, "d")
              .replace(/\\s+/g, " ")
              .trim();
            const looksLikeReplySummary = node => {
              if (!node || hasRealHref(node) || node.closest("a[href]")) return false;
              const text = fold(node.innerText || node.textContent || "");
              if (!text || text.length > 220) return false;
              if (text.includes("phan hoi") && (text.includes("da tra loi") || /\\b\\d+\\s+phan hoi\\b/.test(text))) return true;
              if ((text.includes("tra loi") || text.includes("cau tra loi")) && /\\b\\d+\\s+(?:tra loi|cau tra loi)\\b/.test(text)) return true;
              if (text.includes("repl") && (text.includes("replied") || text.includes("view") || text.includes("see") || text.includes("previous") || /\\b\\d+\\s+repl(?:y|ies)\\b/.test(text))) return true;
              return false;
            };
            const button = el.closest("[role='button']");
            if (button && !hasRealHref(button) && !button.closest("a[href]")) return button;
            const tab = el.closest("[tabindex]:not([tabindex='-1'])");
            if (tab && !hasRealHref(tab) && !tab.closest("a[href]")) return tab;
            let current = el;
            for (let i = 0; current && i < 7; i += 1, current = current.parentElement) {
              if (looksLikeReplySummary(current)) return current;
            }
            return hasRealHref(el) || el.closest("a[href]") ? null : el;
            """,
            el,
        )
        if target:
            el = target
        else:
            return False
    except Exception:
        pass

    if _is_reaction_viewer_trigger(driver, el):
        return False

    try:
        driver.execute_script(
            """
            const el = arguments[0];
            const topPad = Math.max(0, Number(arguments[1] || 96));
            const bottomPad = Math.max(0, Number(arguments[2] || 160));
            if (!el) return;

            const scrollableAncestor = node => {
              for (let cur = node && node.parentElement; cur && cur !== document.body; cur = cur.parentElement) {
                const style = window.getComputedStyle(cur);
                const oy = String(style && style.overflowY || "").toLowerCase();
                if ((oy === "auto" || oy === "scroll" || oy === "overlay") && cur.scrollHeight - cur.clientHeight > 40) {
                  return cur;
                }
              }
              return null;
            };
            const revealInside = (viewTop, viewBottom, applyDelta) => {
              const rect = el.getBoundingClientRect();
              if (!rect || rect.width <= 0 || rect.height <= 0) return;
              let delta = 0;
              if (rect.top < viewTop + topPad) {
                delta = rect.top - (viewTop + topPad);
              } else if (rect.bottom > viewBottom - bottomPad) {
                delta = rect.bottom - (viewBottom - bottomPad);
              }
              if (Math.abs(delta) > 2) applyDelta(delta);
            };

            const scroller = scrollableAncestor(el);
            if (scroller) {
              const sr = scroller.getBoundingClientRect();
              revealInside(sr.top, sr.bottom, delta => {
                const maxTop = Math.max(0, scroller.scrollHeight - scroller.clientHeight);
                scroller.scrollTop = Math.max(0, Math.min(maxTop, scroller.scrollTop + delta));
              });
            } else {
              revealInside(0, window.innerHeight || document.documentElement.clientHeight || 0, delta => {
                window.scrollBy({top: delta, left: 0, behavior: "instant"});
              });
            }
            """,
            el,
            _env_int("COMMENTS_EXPAND_SAFE_CLICK_TOP_PAD", 96),
            _env_int("COMMENTS_EXPAND_SAFE_CLICK_BOTTOM_PAD", 160),
        )
        try:
            scroll_sleep = float(os.environ.get("COMMENTS_EXPAND_SAFE_CLICK_SCROLL_SLEEP", "0.006"))
        except (TypeError, ValueError):
            scroll_sleep = 0.006
        time.sleep(max(0.0, scroll_sleep))
    except Exception:
        pass

    try:
        el.click()
        return True
    except (StaleElementReferenceException, ElementClickInterceptedException, ElementNotInteractableException):
        pass
    except Exception:
        pass

    try:
        driver.execute_script("arguments[0].click();", el)
        return True
    except (StaleElementReferenceException, JavascriptException):
        return False
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Expand text detection
# ---------------------------------------------------------------------------

def is_expand_text(text: str) -> bool:
    t = normalize_text(text)
    folded = fold_text(text)
    if not t:
        return False
    if any(skip in t for skip in SKIP_PATTERNS):
        return False
    if any(skip in folded for skip in SKIP_FOLD_PATTERNS):
        return False
    if len(folded) > 260 and not _looks_like_reply_summary_text(folded):
        return False
    if any(pat in t for pat in EXPAND_PATTERNS):
        return True
    if any(pat in folded for pat in EXPAND_FOLD_PATTERNS):
        return True
    if _looks_like_reply_summary_text(folded):
        return True
    if "view" in t and "repl" in t:
        return True
    if "see" in t and "repl" in t:
        return True
    if "xem" in t and ("bình luận" in t or "phản hồi" in t or "trả lời" in t or "thêm" in t):
        return True
    return False


_REPLY_COUNT_RE = re.compile(r"\b\d+\s+(?:phan hoi|tra loi|cau tra loi|reply|replies)\b")


def _looks_like_reply_summary_text(folded_text: str) -> bool:
    t = folded_text or ""
    if not t or len(t) > 260:
        return False

    if "phan hoi" in t:
        return (
            "da tra loi" in t
            or "xem" in t
            or "tat ca" in t
            or "truoc" in t
            or bool(_REPLY_COUNT_RE.search(t))
        )

    if "tra loi" in t or "cau tra loi" in t:
        return "xem" in t or "tat ca" in t or bool(_REPLY_COUNT_RE.search(t))

    if "repl" in t:
        return (
            "replied" in t
            or "view" in t
            or "see" in t
            or "previous" in t
            or bool(_REPLY_COUNT_RE.search(t))
        )

    return False


# ---------------------------------------------------------------------------
# Viewport helpers
# ---------------------------------------------------------------------------

def _get_relative_top(driver, el, container) -> Optional[float]:
    try:
        return _eval_js(
            driver,
            """
            const el = arguments[0], container = arguments[1];
            if (!el) return null;
            const r = el.getBoundingClientRect();
            if (!r) return null;
            if (!container) return r.top;
            const cr = container.getBoundingClientRect();
            if (!cr) return null;
            return r.top - cr.top;
            """,
            el, container,
        )
    except Exception:
        return None


def _is_near_viewport(driver, el, container, margin_px: int) -> bool:
    try:
        return bool(_eval_js(
            driver,
            """
            const el = arguments[0], container = arguments[1], margin = arguments[2] || 0;
            if (!el) return false;
            const r = el.getBoundingClientRect();
            if (!r) return false;
            if (!container) {
              return r.bottom >= -margin && r.top <= (window.innerHeight || 0) + margin;
            }
            const cr = container.getBoundingClientRect();
            if (!cr) return false;
            const top = r.top - cr.top, bottom = r.bottom - cr.top;
            return bottom >= -margin && top <= (cr.height || 0) + margin;
            """,
            el, container, int(margin_px),
        ))
    except Exception:
        return False


def _find_articles_near_viewport(driver, root, container, margin_px: int) -> List:
    try:
        return driver.execute_script(
            """
            const root = arguments[0], container = arguments[1], margin = arguments[2] || 0;
            if (!root) return [];
            const els = root.querySelectorAll("[role='article']");
            const res = [];
            let viewHeight = window.innerHeight || 0, cTop = 0;
            if (container) {
              const cr = container.getBoundingClientRect();
              viewHeight = cr && cr.height ? cr.height : viewHeight;
              cTop = cr && typeof cr.top === 'number' ? cr.top : 0;
            }
            for (const el of els) {
              try {
                const r = el.getBoundingClientRect();
                const top = container ? (r.top - cTop) : r.top;
                const bottom = container ? (r.bottom - cTop) : r.bottom;
                if (bottom >= -margin && top <= viewHeight + margin) res.push(el);
              } catch (e) {}
            }
            return res;
            """,
            root, container, int(margin_px),
        )
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Find expand buttons
# ---------------------------------------------------------------------------

def find_expand_buttons(root) -> List:
    xpath = """
    .//*[self::div or self::span or self::a]
      [@role='button' or @role='link' or self::a
       or contains(normalize-space(.), 'phản hồi')
       or contains(normalize-space(.), 'trả lời')
       or (starts-with(normalize-space(.), 'View ') and contains(normalize-space(.), 'repl'))
       or (starts-with(normalize-space(.), 'See ') and contains(normalize-space(.), 'repl'))
       or contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'reply')
       or contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'replied')]
    """
    candidates = root.find_elements(By.XPATH, xpath)
    results, seen = [], set()

    for el in candidates:
        try:
            text = normalize_text(el.text)
            aria = normalize_text(el.get_attribute("aria-label"))
            title = normalize_text(el.get_attribute("title"))
            merged = " | ".join(x for x in [text, aria, title] if x)

            if not is_expand_text(merged):
                continue
            if not element_visible_enabled(el):
                continue
            try:
                has_href = bool(root.parent.execute_script(
                    """
                    const el = arguments[0];
                    const linked = el && el.closest && el.closest("a[href], [role='link'][href]");
                    const href = String((linked && linked.getAttribute("href")) || (el && el.getAttribute && el.getAttribute("href")) || "").trim();
                    return !!href && !href.toLowerCase().startsWith("javascript:") && !href.startsWith("#");
                    """,
                    el,
                ))
            except Exception:
                has_href = False
            if has_href:
                continue

            key = (merged, el.get_attribute("outerHTML")[:300])
            if key in seen:
                continue
            seen.add(key)
            results.append(el)
        except StaleElementReferenceException:
            continue
        except Exception:
            continue

    return results


def _expand_button_label(btn) -> str:
    return (
        normalize_text(getattr(btn, "text", "") or "")
        or normalize_text(btn.get_attribute("aria-label"))
        or normalize_text(btn.get_attribute("title"))
        or normalize_text(btn.get_attribute("innerText"))
    )


def _expand_button_fingerprint(btn, label: str) -> str:
    try:
        y = btn.location.get("y")
    except Exception:
        y = ""
    try:
        outer = btn.get_attribute("outerHTML") or ""
    except Exception:
        outer = ""
    return f"{label}|{y}|{outer[:220]}"


def _click_expand_buttons(
    driver,
    buttons: List,
    clicked_fingerprints: Set[str],
    *,
    container=None,
    margin_px: int | None = None,
    max_clicks: int = EXPAND_MAX_CLICKS_PER_ROUND,
    pause_after_click: float = 0.35,
) -> int:
    total_clicked = 0
    for btn in buttons:
        try:
            if not element_visible_enabled(btn):
                continue
            if _is_reaction_viewer_trigger(driver, btn):
                continue
            if margin_px is not None and not _is_near_viewport(driver, btn, container, margin_px):
                continue
            label = _expand_button_label(btn)
            if not label or not is_expand_text(label):
                continue
            fp = _expand_button_fingerprint(btn, label)
            if fp in clicked_fingerprints:
                continue
            if safe_click(driver, btn):
                clicked_fingerprints.add(fp)
                total_clicked += 1
                time.sleep(pause_after_click)
                if total_clicked >= max_clicks:
                    return total_clicked
        except StaleElementReferenceException:
            continue
        except Exception:
            continue
    return total_clicked


# ---------------------------------------------------------------------------
# Select "All comments" filter
# ---------------------------------------------------------------------------
def select_all_comments_filter(driver, root=None, timeout=3, click_comments_tab=True) -> bool:
    wait = WebDriverWait(driver, timeout)
    scope = root if root is not None else driver

    ALL_COMMENTS_KEYWORDS = ["tất cả bình luận", "tất cả các bình luận", "all comments"]
    TRIGGER_KEYWORDS = ["phù hợp nhất", "phù hợp", "mới nhất", "relevant", "top comments", "newest"]
    COMMENT_TAB_KEYWORDS = ["bình luận", "comments"]
    NEGATIVE_TRIGGER_KEYWORDS = [
        "cảm xúc",
        "reaction",
        "all reactions",
        "xem thêm",
        "thích",
        "like",
        "haha",
        "love",
        "wow",
        "sad",
        "angry",
        "care",
        "chia sẻ",
        "share",
        "theo dõi",
        "follow",
        "báo cáo",
        "report",
        "chặn",
        "block",
    ]

    def merged_text(el):
        try:
            return " ".join(
                filter(
                    None,
                    [
                        el.text,
                        el.get_attribute("aria-label"),
                        el.get_attribute("title"),
                        el.get_attribute("data-tooltip-content"),
                    ],
                )
            ).strip().lower()
        except Exception:
            return ""

    def has_any_keyword(text, keywords):
        return any(keyword in text for keyword in keywords)

    def env_float(name, default):
        try:
            return float(os.environ.get(name, default))
        except (TypeError, ValueError):
            return float(default)

    def has_label_keyword(text, keywords):
        text = normalize_text(text)
        if not text:
            return False
        return any(text == keyword or text.startswith(f"{keyword} ") for keyword in keywords)

    def primary_label_text(el):
        try:
            spans = el.find_elements(By.CSS_SELECTOR, "span[dir='auto'], span")
            for span in spans:
                if not element_visible_enabled(span):
                    continue
                text = normalize_text(span.text or span.get_attribute("innerText"))
                if text:
                    return text
        except Exception:
            pass

        try:
            raw = el.get_attribute("innerText") or el.text or ""
            for line in str(raw).splitlines():
                text = normalize_text(line)
                if text:
                    return text
        except Exception:
            pass
        return ""

    def find_by_text(search_scope, keywords, tags=("span", "div", "a")):
        try:
            items = search_scope.find_elements(
                By.XPATH,
                ".//*[@role='menuitem' or @role='menuitemradio' or @role='menuitemcheckbox' or @role='option' or @role='button' or @tabindex]",
            )
        except Exception:
            items = []

        for item in items:
            try:
                if has_label_keyword(primary_label_text(item), keywords):
                    return item
            except Exception:
                continue

        tag_selector = " | ".join(f".//{t}" for t in tags)
        elements = search_scope.find_elements(By.XPATH, tag_selector)
        for el in elements:
            try:
                if has_label_keyword(merged_text(el), keywords):
                    try:
                        return el.find_element(
                            By.XPATH,
                            "ancestor-or-self::*[@role='menuitem' or @role='menuitemradio' or @role='menuitemcheckbox' or @role='option' or @role='button' or @tabindex][1]",
                        )
                    except Exception:
                        return el
            except Exception:
                continue
        return None

    def find_clickable_by_keywords(search_scope, keywords):
        try:
            elements = search_scope.find_elements(
                By.XPATH,
                ".//*[@role='button' or @role='tab' or @aria-haspopup='menu']",
            )
        except Exception:
            elements = []

        scored = []
        for el in elements:
            try:
                if not element_visible_enabled(el):
                    continue
                text = merged_text(el)
                if not text:
                    continue
                if has_any_keyword(text, NEGATIVE_TRIGGER_KEYWORDS):
                    continue
                if not has_any_keyword(text, keywords):
                    continue
                priority = 0 if has_label_keyword(primary_label_text(el), ALL_COMMENTS_KEYWORDS) else 1
                scored.append((priority, len(text), el))
            except Exception:
                continue

        scored.sort(key=lambda item: (item[0], item[1]))
        return scored[0][2] if scored else None

    def js_click(el):
        try:
            rect = driver.execute_script(
                """
                const el = arguments[0];
                el.scrollIntoView({block: 'nearest', inline: 'nearest', behavior: 'instant'});
                const rect = el.getBoundingClientRect();
                return {
                  x: rect.left + rect.width / 2,
                  y: rect.top + rect.height / 2,
                  width: rect.width,
                  height: rect.height
                };
                """,
                el,
            )
            if isinstance(rect, dict) and rect.get("width", 0) > 0 and rect.get("height", 0) > 0:
                try:
                    driver.execute_cdp_cmd("Page.bringToFront", {})
                    driver.execute_cdp_cmd("Input.dispatchMouseEvent", {
                        "type": "mouseMoved",
                        "x": float(rect["x"]),
                        "y": float(rect["y"]),
                    })
                    driver.execute_cdp_cmd("Input.dispatchMouseEvent", {
                        "type": "mousePressed",
                        "x": float(rect["x"]),
                        "y": float(rect["y"]),
                        "button": "left",
                        "clickCount": 1,
                    })
                    driver.execute_cdp_cmd("Input.dispatchMouseEvent", {
                        "type": "mouseReleased",
                        "x": float(rect["x"]),
                        "y": float(rect["y"]),
                        "button": "left",
                        "clickCount": 1,
                    })
                except Exception:
                    pass
        except Exception:
            pass
        driver.execute_script(
            """
            const el = arguments[0];
            el.scrollIntoView({block: 'nearest', inline: 'nearest', behavior: 'instant'});
            const rect = el.getBoundingClientRect();
            const opts = {
              bubbles: true,
              cancelable: true,
              view: window,
              clientX: rect.left + rect.width / 2,
              clientY: rect.top + rect.height / 2
            };
            for (const type of ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click']) {
              el.dispatchEvent(new MouseEvent(type, opts));
            }
            if (typeof el.click === 'function') el.click();
            """,
            el,
        )

    def scroll_into_view(el):
        """Scroll element vào giữa viewport trước khi thao tác."""
        driver.execute_script(
            "arguments[0].scrollIntoView({block: 'nearest', inline: 'nearest', behavior: 'instant'});",
            el
        )
        time.sleep(max(0.0, env_float("COMMENTS_SORT_SCROLL_INTO_VIEW_SLEEP", 0.05)))

    def click_comments_tab_if_present():
        scopes = [scope]
        if root is not None:
            scopes.append(driver)

        for search_scope in scopes:
            tab = find_clickable_by_keywords(search_scope, COMMENT_TAB_KEYWORDS)
            if tab is None:
                continue

            try:
                selected = (tab.get_attribute("aria-selected") or "").strip().lower() == "true"
                pressed = (tab.get_attribute("aria-pressed") or "").strip().lower() == "true"
                expanded = (tab.get_attribute("aria-expanded") or "").strip().lower() == "true"
            except Exception:
                selected = pressed = expanded = False

            if selected or pressed or expanded:
                return True

            try:
                scroll_into_view(tab)
                js_click(tab)
                time.sleep(0.1)
                return True
            except Exception:
                continue
        return False

    def reset_comment_surface_to_top():
        if root is None:
            return
        try:
            container = find_comment_scroll_target(driver, root)
        except Exception:
            container = None
        try:
            if container is not None:
                driver.execute_script("arguments[0].scrollTop = 0;", container)
                time.sleep(0.05)
                return
        except Exception:
            pass
        try:
            first_article = root.find_element(By.CSS_SELECTOR, "[role='article'][aria-label]")
            scroll_into_view(first_article)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 1. Tìm trigger — có thể cần scroll mới thấy
    # ------------------------------------------------------------------
    if click_comments_tab:
        click_comments_tab_if_present()
    reset_comment_surface_to_top()

    trigger = find_clickable_by_keywords(scope, TRIGGER_KEYWORDS + ALL_COMMENTS_KEYWORDS)
    if trigger is None and root is not None:
        trigger = find_clickable_by_keywords(driver, TRIGGER_KEYWORDS + ALL_COMMENTS_KEYWORDS)

    if trigger is None:
        return False

    # Kiểm tra đã đúng filter chưa
    trigger_text = merged_text(trigger)
    if has_label_keyword(primary_label_text(trigger) or trigger_text, ALL_COMMENTS_KEYWORDS):
        return True

    # ------------------------------------------------------------------
    # 2. Scroll đến trigger → click mở dropdown
    # ------------------------------------------------------------------
    try:
        scroll_into_view(trigger)
        js_click(trigger)
    except Exception:
        return False

    # ------------------------------------------------------------------
    # 3. Chờ menu → scroll đến item → click
    # ------------------------------------------------------------------
    try:
        def click_all_comments_item(d):
            menus = d.find_elements(By.XPATH, "//*[@role='menu' or @role='listbox' or @role='dialog' or @role='presentation']")
            for menu in menus:
                item = find_by_text(menu, ALL_COMMENTS_KEYWORDS, tags=("span", "div", "a"))
                if item:
                    scroll_into_view(item)  # ← đảm bảo item trong viewport
                    js_click(item)
                    return True

            items = d.find_elements(
                By.XPATH,
                "//*[@role='menuitem' or @role='menuitemradio' or @role='menuitemcheckbox' or @role='option' or @role='button' or @tabindex]",
            )
            for item in items:
                if has_label_keyword(primary_label_text(item), ALL_COMMENTS_KEYWORDS):
                    scroll_into_view(item)
                    js_click(item)
                    return True

            return False

        wait.until(click_all_comments_item)
        time.sleep(max(0.0, env_float("COMMENTS_ALL_COMMENTS_CLICK_SETTLE_SLEEP", 0.1)))
        return True

    except TimeoutException:
        return False
# ---------------------------------------------------------------------------
# Expand comments near viewport
# ---------------------------------------------------------------------------

def expand_comments_near_viewport(
    driver,
    root,
    clicked_fingerprints: Set[str],
    *,
    margin_px: int = EXPAND_VIEWPORT_MARGIN_PX,
    max_clicks: int = EXPAND_MAX_CLICKS_PER_ROUND,
    pause_after_click: float = 0.35,
) -> int:
    if root is None:
        return 0

    container = find_comment_scroll_target(driver, root)
    articles = _find_articles_near_viewport(driver, root, container, margin_px=margin_px)
    total_clicked = 0

    try:
        root_buttons = find_expand_buttons(root)
    except (StaleElementReferenceException, Exception):
        root_buttons = []
    total_clicked += _click_expand_buttons(
        driver,
        root_buttons,
        clicked_fingerprints,
        container=container,
        margin_px=margin_px,
        max_clicks=max_clicks,
        pause_after_click=pause_after_click,
    )
    if total_clicked >= max_clicks:
        return total_clicked

    for article in articles:
        try:
            buttons = find_expand_buttons(article)
        except StaleElementReferenceException:
            continue
        except Exception:
            continue

        clicked = _click_expand_buttons(
            driver,
            buttons,
            clicked_fingerprints,
            container=container,
            margin_px=margin_px,
            max_clicks=max_clicks - total_clicked,
            pause_after_click=pause_after_click,
        )
        total_clicked += clicked
        if total_clicked >= max_clicks:
            return total_clicked

    return total_clicked


# ---------------------------------------------------------------------------
# Expand post content (See more in post body)
# ---------------------------------------------------------------------------

def expand_post_content_until_done(
    driver,
    post_element,
    source_url: str,
    *,
    pause_after_click: float = 0.2,
    max_rounds: int = 3,
) -> int:
    from src.profile.post_helpers import find_post_content_roots  # local import để tránh circular

    total_clicked = 0
    clicked_fingerprints: Set[str] = set()

    for _ in range(max_rounds):
        clicked_this_round = 0
        for root in find_post_content_roots(post_element, source_url):
            try:
                buttons = root.find_elements(
                    By.XPATH,
                    ".//*[self::div or self::span]"
                    "[@role='button' and (normalize-space(.)='Xem thêm' or normalize-space(.)='See more')]",
                )
            except Exception:
                continue

            for btn in buttons:
                try:
                    if not element_visible_enabled(btn):
                        continue
                    label = normalize_text(btn.text) or normalize_text(btn.get_attribute("aria-label"))
                    if not label:
                        continue
                    if not any(pat == label for pat in POST_SEE_MORE_PATTERNS):
                        continue
                    fp = f"{label}|{btn.get_attribute('outerHTML')[:200]}"
                    if fp in clicked_fingerprints:
                        continue
                    if safe_click(driver, btn):
                        clicked_fingerprints.add(fp)
                        clicked_this_round += 1
                        total_clicked += 1
                        time.sleep(pause_after_click)
                except StaleElementReferenceException:
                    continue
                except Exception:
                    continue

        if clicked_this_round == 0:
            break

    return total_clicked



# ---------------------------------------------------------------------------
# Expand all comments (full loop)
# ---------------------------------------------------------------------------

def expand_comments_until_done(
    driver,
    post_element,
    source_url: str,
    *,
    pause_after_click: float = 0.2,
    max_rounds: int = 3,
) -> int:
    from src.profile.post_helpers import find_post_content_roots  # local import để tránh circular

    total_clicked = 0
    clicked_fingerprints: Set[str] = set()

    for _ in range(max_rounds):
        clicked_this_round = 0
        roots = [post_element]
        for root in find_post_content_roots(post_element, source_url):
            if root not in roots:
                roots.append(root)

        for root in roots:
            try:
                buttons = find_expand_buttons(root)
            except Exception:
                continue

            clicked = _click_expand_buttons(
                driver,
                buttons,
                clicked_fingerprints,
                max_clicks=EXPAND_MAX_CLICKS_PER_ROUND,
                pause_after_click=pause_after_click,
            )
            clicked_this_round += clicked
            total_clicked += clicked

        if clicked_this_round == 0:
            break
    logger.info(f"Total: {total_clicked} clicks")
    return total_clicked

def _expand_comments_until_done(
    driver,
    root,
    pause_after_click: float = 0.35,
    max_rounds: int = 50,
) -> int:
    total_clicked = 0
    clicked_fingerprints: Set[str] = set()

    for _ in range(max_rounds):
        try:
            buttons = find_expand_buttons(root)
        except (StaleElementReferenceException, Exception):
            break

        if not buttons:
            break

        clicked_this_round = _click_expand_buttons(
            driver,
            buttons,
            clicked_fingerprints,
            max_clicks=EXPAND_MAX_CLICKS_PER_ROUND,
            pause_after_click=pause_after_click,
        )
        total_clicked += clicked_this_round

        if clicked_this_round == 0:
            break

    return total_clicked


# ---------------------------------------------------------------------------
# Prune processed comment articles
# ---------------------------------------------------------------------------

def _prune_processed_comment_articles_playwright(
    root: PlaywrightElementAdapter,
    seen: Set[str],
    *,
    keep_anchors: int,
    prune_buffer: int,
    max_articles: int,
    protect_margin_px: int,
) -> int:
    options = {
        "seenKeys": sorted(str(key).strip() for key in seen if str(key).strip()),
        "keepAnchors": max(1, int(keep_anchors)),
        "pruneBuffer": max(0, int(prune_buffer)),
        "maxArticles": max(1, int(max_articles)),
        "protectMarginPx": max(0, int(protect_margin_px)),
    }
    removed = root._locator.evaluate(
            """
            (root, options) => {
              if (!root) return 0;

              const anchors = Array.from(root.querySelectorAll("a[href*='comment_id=']"));
              const keepAnchors = Math.max(1, Number(options.keepAnchors) || 1);
              const pruneBuffer = Math.max(0, Number(options.pruneBuffer) || 0);
              if (anchors.length <= keepAnchors + pruneBuffer) return 0;

              const cutoffIndex = anchors.length - keepAnchors;
              const cutoffAnchor = anchors[cutoffIndex];
              if (!cutoffAnchor) return 0;

              const findScrollContainer = element => {
                let current = element && element.parentElement;
                for (let depth = 0; current && depth < 32; depth += 1) {
                  try {
                    const style = window.getComputedStyle(current);
                    const overflowY = String(style && style.overflowY || "").toLowerCase();
                    const scrollable = overflowY === "auto" || overflowY === "scroll" || overflowY === "overlay";
                    if (scrollable && current.scrollHeight - current.clientHeight > 40) return current;
                  } catch (error) {}
                  current = current.parentElement;
                }
                return null;
              };
              const container = findScrollContainer(cutoffAnchor);
              const relativeTop = element => {
                if (!element || !element.isConnected) return null;
                const rect = element.getBoundingClientRect();
                if (!rect) return null;
                if (!container) return rect.top;
                const containerRect = container.getBoundingClientRect();
                return containerRect ? rect.top - containerRect.top : null;
              };
              const nearViewport = element => {
                if (!element || !element.isConnected) return false;
                const rect = element.getBoundingClientRect();
                if (!rect) return false;
                const margin = Math.max(0, Number(options.protectMarginPx) || 0);
                if (!container) {
                  return rect.bottom >= -margin && rect.top <= (window.innerHeight || 0) + margin;
                }
                const containerRect = container.getBoundingClientRect();
                if (!containerRect) return false;
                const top = rect.top - containerRect.top;
                const bottom = rect.bottom - containerRect.top;
                return bottom >= -margin && top <= (containerRect.height || 0) + margin;
              };
              const commentKeys = anchor => {
                const href = String(anchor && (anchor.getAttribute("href") || anchor.href) || "").trim();
                if (!href) return [];
                try {
                  const url = new URL(href, window.location.href);
                  return [
                    url.searchParams.get("reply_comment_id"),
                    url.searchParams.get("comment_id")
                  ].filter(Boolean).map(String);
                } catch (error) {
                  const values = [];
                  for (const name of ["reply_comment_id", "comment_id"]) {
                    const match = href.match(new RegExp(`[?&]${name}=([^&#]+)`));
                    if (match && match[1]) {
                      try { values.push(decodeURIComponent(match[1])); }
                      catch (decodeError) { values.push(match[1]); }
                    }
                  }
                  return values;
                }
              };

              const beforeTop = relativeTop(cutoffAnchor);
              if (beforeTop === null) return 0;

              const seenKeys = new Set((options.seenKeys || []).map(value => String(value).trim()).filter(Boolean));
              const removedArticles = new Set();
              const maxArticles = Math.max(1, Number(options.maxArticles) || 1);
              let removed = 0;

              for (let index = 0; index < cutoffIndex && removed < maxArticles; index += 1) {
                const anchor = anchors[index];
                const keys = commentKeys(anchor);
                if (!keys.some(key => seenKeys.has(key))) continue;

                const article = anchor.closest && anchor.closest("[role='article']");
                if (
                  !article
                  || article.contains(cutoffAnchor)
                  || removedArticles.has(article)
                  || nearViewport(article)
                ) continue;

                removedArticles.add(article);
                article.remove();
                removed += 1;
              }

              if (removed <= 0) return 0;
              const afterTop = relativeTop(cutoffAnchor);
              if (afterTop === null) return removed;

              const delta = afterTop - beforeTop;
              if (Math.abs(delta) >= 1) {
                if (container) container.scrollTop = (container.scrollTop || 0) + delta;
                else window.scrollBy(0, delta);
              }
              return removed;
            }
            """,
        options,
    )

    try:
        return max(0, int(removed or 0))
    except (TypeError, ValueError):
        return 0


def prune_processed_comment_articles(
    driver,
    root,
    seen: Set[str],
    *,
    keep_anchors: int = KEEP_ANCHORS,
    prune_buffer: int = PRUNE_BUFFER,
    max_articles: int = PRUNE_MAX_ARTICLES_PER_ROUND,
    protect_margin_px: int = EXPAND_VIEWPORT_MARGIN_PX,
) -> int:
    if root is None:
        return 0
    if isinstance(root, PlaywrightElementAdapter):
        return _prune_processed_comment_articles_playwright(
            root,
            seen,
            keep_anchors=keep_anchors,
            prune_buffer=prune_buffer,
            max_articles=max_articles,
            protect_margin_px=protect_margin_px,
        )

    try:
        anchors = root.find_elements(By.CSS_SELECTOR, "a[href*='comment_id=']")
    except Exception:
        anchors = []

    if len(anchors) <= (keep_anchors + prune_buffer):
        return 0

    cutoff_index = max(0, len(anchors) - keep_anchors)
    if cutoff_index <= 0 or cutoff_index >= len(anchors):
        return 0

    cutoff_anchor = anchors[cutoff_index]
    container = find_comment_scroll_target(driver, root)
    before_top = _get_relative_top(driver, cutoff_anchor, container)
    if before_top is None:
        return 0

    prunable: List = []
    seen_articles: Set[str] = set()

    for a in anchors[:cutoff_index]:
        try:
            href = (a.get_attribute("href") or "").strip()
            ids = extract_comment_ids_from_href(href)
            key = str(ids.get("reply_comment_id") or ids.get("comment_id") or "").strip()
            if not key or key not in seen:
                continue

            article = _closest_comment_article(driver, a)
            if article is None:
                continue
            if _is_near_viewport(driver, article, container, margin_px=protect_margin_px):
                continue

            fp = article.get_attribute("outerHTML")[:220]
            if fp in seen_articles:
                continue
            seen_articles.add(fp)
            prunable.append(article)
            if len(prunable) >= max_articles:
                break
        except StaleElementReferenceException:
            continue
        except Exception:
            continue

    removed = 0
    for article in prunable:
        try:
            _eval_js(driver, "const el = arguments[0]; if (el && el.remove) el.remove();", article)
            removed += 1
        except Exception:
            continue

    if removed <= 0:
        return 0

    after_top = _get_relative_top(driver, cutoff_anchor, container)
    if after_top is None:
        return removed

    delta = after_top - before_top
    if abs(delta) >= 1:
        try:
            if container is not None:
                _eval_js(
                    driver,
                    "const c = arguments[0]; c.scrollTop = (c.scrollTop || 0) + arguments[1];",
                    container, float(delta),
                )
            else:
                _eval_js(driver, "window.scrollBy(0, arguments[0]);", float(delta))
        except Exception:
            pass

    return removed


def _closest_comment_article(driver, el):
    try:
        return driver.execute_script("return arguments[0].closest('[role=\"article\"]');", el)
    except Exception:
        return None
