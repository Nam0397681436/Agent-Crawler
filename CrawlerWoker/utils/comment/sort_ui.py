"""Sort-menu UI helpers for Facebook comment crawling."""

from __future__ import annotations

import time

from src.driver.browser_compat import By, ElementClickInterceptedException
from src.driver.playwright_native import is_playwright_driver, page_for

from .clicks import safe_click
from .runtime import _env_float
from .utils import _menuitem_xpaths_for_texts, _visible


def _sleep_after_all_comments_click(driver) -> None:
    seconds = max(0.05, _env_float("COMMENTS_ALL_COMMENTS_CLICK_SETTLE_SLEEP", 0.25))
    if is_playwright_driver(driver):
        try:
            page_for(driver).wait_for_timeout(int(seconds * 1000))
            return
        except Exception:
            pass
    time.sleep(seconds)


def _choose_all_comments_playwright(driver, labels: list[str]) -> bool:
    page = page_for(driver)
    find_and_click_script = """
    (labelsInput) => {
      const labels = labelsInput.map(s => String(s || '').trim().toLowerCase()).filter(Boolean);
      const norm = value => String(value || '').replace(/\\s+/g, ' ').trim().toLowerCase();
      const roleOk = new Set(['menuitem', 'menuitemradio', 'menuitemcheckbox', 'option', 'button']);
      const visible = el => {
        if (!el || !el.isConnected) return false;
        const rect = el.getBoundingClientRect();
        const style = window.getComputedStyle(el);
        return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
      };
      const firstLineOf = el => {
        const raw = String(el.innerText || el.textContent || '');
        return raw.split(/\\n+/).map(norm).find(Boolean) || '';
      };
      const primaryLabelOf = el => {
        const spans = Array.from(el.querySelectorAll('span[dir="auto"], span')).filter(visible);
        for (const span of spans) {
          const text = norm(span.innerText || span.textContent);
          if (text) return text;
        }
        return firstLineOf(el) || norm(el.getAttribute('aria-label')) || norm(el.getAttribute('title'));
      };
      const scopes = Array.from(document.querySelectorAll('[role="menu"], [role="listbox"], [role="dialog"], [role="presentation"]'));
      if (!scopes.length) scopes.push(document.body);
      const candidates = [];
      for (const scope of scopes) {
        const nodes = Array.from(scope.querySelectorAll('[role], [tabindex], [aria-checked]')).filter(visible);
        for (const node of nodes) {
          const role = norm(node.getAttribute('role'));
          if (!roleOk.has(role) && !node.hasAttribute('tabindex') && !node.hasAttribute('aria-checked')) continue;
          const primaryText = primaryLabelOf(node);
          if (!primaryText || primaryText.length > 120) continue;
          if (!labels.some(label => primaryText === label || primaryText.includes(label))) continue;
          candidates.push({
            node,
            score: (labels.some(label => primaryText === label) ? 0 : 10) + Math.min(primaryText.length, 120)
          });
        }
      }
      candidates.sort((a, b) => a.score - b.score);
      const el = candidates.length ? candidates[0].node : null;
      if (!el) return false;
      try { el.scrollIntoView({block: 'nearest', inline: 'nearest', behavior: 'instant'}); } catch (e) {}
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
      return true;
    }
    """
    try:
        clicked = bool(page.evaluate(find_and_click_script, labels))
    except Exception:
        return False
    if clicked:
        _sleep_after_all_comments_click(driver)
    return clicked


def choose_all_comments_unified(driver, timeout=1):
    """
    After the sort menu opens, pick the 'All comments' option. Search at <body>-level.
    """
    ALL_COMMENTS_TEXTS = [
        "T\u1ea5t c\u1ea3 b\u00ecnh lu\u1eadn",
        "T\u1ea5t c\u1ea3 c\u00e1c b\u00ecnh lu\u1eadn",
        "Tất cả bình luận",  # VI
        "Tất cả các bình luận",
        "All comments",      # EN
    ]

    if is_playwright_driver(driver):
        end = time.time() + max(0.1, float(timeout))
        while time.time() < end:
            if _choose_all_comments_playwright(driver, ALL_COMMENTS_TEXTS):
                return True
            time.sleep(0.1)
        raise ElementClickInterceptedException("Không click được option 'All comments' (global).")

    def find_option_by_js():
        try:
            return driver.execute_script(
                """
                const labels = arguments[0].map(s => String(s || '').trim().toLowerCase()).filter(Boolean);
                const norm = value => String(value || '').replace(/\\s+/g, ' ').trim().toLowerCase();
                const roleOk = new Set(['menuitem', 'menuitemradio', 'menuitemcheckbox', 'option', 'button']);
                const visible = el => {
                  if (!el || !el.isConnected) return false;
                  const rect = el.getBoundingClientRect();
                  const style = window.getComputedStyle(el);
                  return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
                };
                const firstLineOf = el => {
                  const raw = String(el.innerText || el.textContent || '');
                  return raw.split(/\n+/).map(norm).find(Boolean) || '';
                };
                const primaryLabelOf = el => {
                  const spans = Array.from(el.querySelectorAll('span[dir="auto"], span')).filter(visible);
                  for (const span of spans) {
                    const text = norm(span.innerText || span.textContent);
                    if (text) return text;
                  }
                  return firstLineOf(el) || norm(el.getAttribute('aria-label')) || norm(el.getAttribute('title'));
                };
                const scopes = Array.from(document.querySelectorAll('[role="menu"], [role="listbox"], [role="dialog"], [role="presentation"]'));
                if (!scopes.length) scopes.push(document.body);
                const candidates = [];
                for (const scope of scopes) {
                  const nodes = Array.from(scope.querySelectorAll('[role], [tabindex], [aria-checked]')).filter(visible);
                  for (const node of nodes) {
                    const role = norm(node.getAttribute('role'));
                    if (!roleOk.has(role) && !node.hasAttribute('tabindex') && !node.hasAttribute('aria-checked')) continue;
                    const primaryText = primaryLabelOf(node);
                    if (!primaryText || primaryText.length > 120) continue;
                    if (!labels.some(label => primaryText === label || primaryText.includes(label))) continue;
                    candidates.push({
                      node,
                      score: (labels.some(label => primaryText === label) ? 0 : 10) + Math.min(primaryText.length, 120)
                    });
                  }
                }
                candidates.sort((a, b) => a.score - b.score);
                return candidates.length ? candidates[0].node : null;
                """,
                ALL_COMMENTS_TEXTS,
            )
        except Exception:
            return None

    def force_click(el):
        if el is None:
            return False
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
                cdp_clicked = False
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
                    cdp_clicked = True
                except Exception:
                    pass
                if cdp_clicked:
                    _sleep_after_all_comments_click(driver)
                    return True
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
                return true;
                """,
                el,
            )
            _sleep_after_all_comments_click(driver)
            return True
        except Exception:
            try:
                return safe_click(driver, el, sleep_after=max(0.05, _env_float("COMMENTS_ALL_COMMENTS_CLICK_SETTLE_SLEEP", 0.25)))
            except Exception:
                return False

    end = time.time() + max(0.1, float(timeout))
    last_error = None
    xpaths = _menuitem_xpaths_for_texts(ALL_COMMENTS_TEXTS)
    while time.time() < end:
        opt = find_option_by_js()
        if opt is not None and force_click(opt):
            return True

        for xp in xpaths:
            try:
                opt = driver.find_element(By.XPATH, xp)
                if _visible(opt) and force_click(opt):
                    return True
            except Exception as exc:
                last_error = exc
        time.sleep(0.1)

    if last_error:
        raise last_error
    raise ElementClickInterceptedException("Không click được option 'All comments' (global).")




__all__ = ["choose_all_comments_unified"]
