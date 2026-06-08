async def handle_snapshot(
    arguments: dict, browser: BrowserManager
) -> list[types.TextContent]:
    if not browser.page:
        return [
            types.TextContent(type="text", text="Error: No page opened.", isError=True)
        ]

    data = await browser.page.evaluate(
        """
    () => {
        const cssEscape = (value) => {
            if (window.CSS && CSS.escape) return CSS.escape(value);
            return String(value).replace(/["\\\\]/g, "\\\\$&");
        };

        const getText = (el) => {
            return (
                el.innerText ||
                el.textContent ||
                el.value ||
                el.getAttribute('aria-label') ||
                el.getAttribute('title') ||
                ''
            ).trim().replace(/\\s+/g, ' ').slice(0, 120);
        };

        const getSelector = (el) => {
            if (el.id) {
                return `#${cssEscape(el.id)}`;
            }

            const path = [];
            let current = el;

            while (current && current.nodeType === Node.ELEMENT_NODE && current !== document.body) {
                let selector = current.tagName.toLowerCase();

                if (current.className && typeof current.className === 'string') {
                    const classes = current.className
                        .trim()
                        .split(/\\s+/)
                        .filter(Boolean)
                        .slice(0, 2)
                        .map(cssEscape);

                    if (classes.length) {
                        selector += '.' + classes.join('.');
                    }
                }

                const parent = current.parentElement;
                if (parent) {
                    const siblings = Array.from(parent.children)
                        .filter(child => child.tagName === current.tagName);

                    if (siblings.length > 1) {
                        selector += `:nth-of-type(${siblings.indexOf(current) + 1})`;
                    }
                }

                path.unshift(selector);
                current = current.parentElement;
            }

            return path.join(' > ');
        };

        const normalizeHref = (rawHref) => {
            if (!rawHref) return null;

            const trimmed = rawHref.trim();

            if (
                trimmed === '#' ||
                trimmed.toLowerCase().startsWith('javascript:') ||
                trimmed.toLowerCase().startsWith('mailto:') ||
                trimmed.toLowerCase().startsWith('tel:')
            ) {
                return null;
            }

            try {
                return new URL(trimmed, location.href).href;
            } catch (e) {
                return null;
            }
        };

        const links = Array.from(document.querySelectorAll('a[href]'))
            .slice(0, 300)
            .map((a, i) => {
                const rawHref = a.getAttribute('href');
                return {
                    id: i,
                    tag: 'a',
                    text: getText(a),
                    raw_href: rawHref,
                    href: normalizeHref(rawHref),
                    selector: getSelector(a)
                };
            });

        const clickables = Array.from(document.querySelectorAll(
            'button, [role="button"], input[type="button"], input[type="submit"], a[href="#"], a[href^="javascript:"]'
        ))
            .slice(0, 200)
            .map((el, i) => ({
                id: i,
                tag: el.tagName.toLowerCase(),
                text: getText(el),
                selector: getSelector(el)
            }));

        return {
            url: location.href,
            title: document.title,
            links,
            clickables
        };
    }
    """
    )

    return [
        types.TextContent(
            type="text", text=json.dumps(data, ensure_ascii=False, indent=2)
        )
    ]
