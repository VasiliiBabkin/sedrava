use super::{
    assets::Assets,
    external,
    properties::{base_key, declarations, Props, BREAKPOINTS},
    split_target, Node, Page, Site, StaticSite,
};
use crate::model::Result;
use std::{collections::BTreeMap, fmt::Write, path::Path};

const CSS: &str = include_str!("../site.css");

fn html(text: &str) -> String {
    text.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
        .replace('\'', "&#x27;")
}

fn relative(target: &str, page: &Page) -> String {
    let from: Vec<_> = page
        .route
        .split('/')
        .filter(|part| !part.is_empty())
        .collect();
    let to: Vec<_> = target.split('/').collect();
    let common = from
        .iter()
        .zip(&to[..to.len() - 1])
        .take_while(|(a, b)| a == b)
        .count();
    "../".repeat(from.len() - common) + &to[common..].join("/")
}

fn filename(route: &str) -> String {
    format!("{}index.html", &route[1..])
}

struct Render<'a> {
    assets: Assets<'a>,
    css: String,
    count: usize,
    webapp: bool,
}

impl Render<'_> {
    fn css(&mut self, node: &Node, class: &str) {
        let mut base = Props::new();
        let mut media = BTreeMap::<&str, Props>::new();
        for (key, value) in &node.props {
            let (name, bp) = base_key(key);
            match bp {
                Some(bp) => media
                    .entry(bp)
                    .or_default()
                    .insert(name.into(), value.clone()),
                None => base.insert(name.into(), value.clone()),
            };
        }
        if node.kind == "grid" {
            let count = base.insert("columns".into(), "1".into()).unwrap();
            media
                .entry("md")
                .or_default()
                .entry("columns".into())
                .or_insert_with(|| count.parse::<u8>().unwrap().min(2).to_string());
            media
                .entry("lg")
                .or_default()
                .entry("columns".into())
                .or_insert(count);
        }
        let base = declarations(&node.kind, &base);
        if !base.is_empty() {
            writeln!(self.css, ".s-node.{class}{{{base}}}").unwrap();
        }
        for (bp, width) in BREAKPOINTS {
            if let Some(props) = media.get(bp) {
                let css = declarations(&node.kind, props);
                if !css.is_empty() {
                    writeln!(
                        self.css,
                        "@media(min-width:{width}px){{.s-node.{class}{{{css}}}}}"
                    )
                    .unwrap();
                }
            }
        }
    }

    fn node(&mut self, node: &Node, page: &Page, out: &mut String) -> Result<()> {
        self.count += 1;
        let class = format!("n{}", self.count);
        self.css(node, &class);
        let kind = node.kind.as_str();
        let props = &node.props;
        let heading;
        let dynamic = self.webapp && super::webapp::widget(kind).is_some();
        let tag = match kind {
            "button" if dynamic => "button",
            "submit" | "open" | "close" | "navigate" | "back" | "pick" => "button",
            "form" | "dialog" | "select" | "option" => kind,
            "when" | "each" | "row-when" => "section",
            "field" => "output",
            "list" => "ul",
            "heading" => {
                heading = format!("h{}", props["level"]);
                &heading
            }
            "paragraph" => "p",
            "button" | "link" => "a",
            "card" => "article",
            "image" => "img",
            "divider" => "hr",
            "navbar" => "nav",
            "footer" => "footer",
            "callout" => "aside",
            "code" => "pre",
            _ => "div",
        };
        let value = |key| props.get(key).map(String::as_str).unwrap_or("");
        let variant = props
            .get("variant")
            .map(String::as_str)
            .unwrap_or("default");
        let extra = match kind {
            "input" => " s-field",
            "submit" | "open" | "close" | "navigate" | "back" | "pick" => " s-button",
            _ => "",
        };
        if matches!(kind, "input" | "select") {
            out.push_str("<div class=\"s-field\"");
            if let Some(id) = props.get("id").filter(|_| kind == "select") {
                write!(out, " id=\"{}\"", html(id)).unwrap();
            }
            write!(
                out,
                "><label for=\"sdr-field-{class}\">{}</label>",
                html(value("label"))
            )
            .unwrap();
        }
        write!(
            out,
            "<{tag} class=\"s-node s-{kind} {class} v-{variant}{extra} {}\"",
            html(value("class"))
        )
        .unwrap();
        if kind == "image" {
            let src = value("src");
            let src = if external(src, true).is_some() {
                src.to_owned()
            } else {
                relative(
                    &self.assets.image(src).map_err(|e| node.line.error(e.0))?,
                    page,
                )
            };
            write!(out, " loading=\"lazy\" decoding=\"async\" referrerpolicy=\"no-referrer\" src=\"{}\" alt=\"{}\"",
                html(&src), html(value("alt"))).unwrap();
        }
        if kind == "spacer" {
            out.push_str(" aria-hidden=\"true\"");
        }
        if let Some(id) = props.get("id").filter(|_| kind != "select") {
            write!(out, " id=\"{}\"", html(id)).unwrap();
        }
        if let Some(label) = props.get("label").filter(|_| {
            !matches!(
                kind,
                "value" | "input" | "checkbox" | "select" | "list" | "table" | "each"
            )
        }) {
            write!(out, " aria-label=\"{}\"", html(label)).unwrap();
        }
        if let Some(destination) = props.get("to").filter(|_| !dynamic) {
            let (route, suffix) = split_target(destination);
            let href = if self.webapp || route.is_empty() || external(destination, false).is_some()
            {
                destination.to_owned()
            } else {
                relative(&filename(route), page) + suffix
            };
            write!(out, " href=\"{}\"", html(&href)).unwrap();
        }
        if value("target") == "blank" {
            out.push_str(" target=\"_blank\" rel=\"noopener noreferrer\"");
        }
        if dynamic {
            return self.widget(node, page, out, tag, &class);
        }
        out.push('>');
        if !matches!(kind, "image" | "divider") {
            if kind == "code" {
                write!(out, "<code>{}</code>", html(value("text"))).unwrap();
            } else {
                out.push_str(&html(value("text")));
                for child in &node.children {
                    self.node(child, page, out)?;
                }
            }
            write!(out, "</{tag}>").unwrap();
        }
        Ok(())
    }

    fn widget(
        &mut self,
        node: &Node,
        page: &Page,
        out: &mut String,
        tag: &str,
        class: &str,
    ) -> Result<()> {
        let kind = node.kind.as_str();
        let props = &node.props;
        let p = |key| props.get(key).map_or("", String::as_str);
        let attr = |out: &mut String, key, value: &str| {
            write!(out, " {key}=\"{}\"", html(value)).unwrap();
        };
        match kind {
            "button" | "open" | "close" | "back" | "navigate" | "submit" | "pick" => {
                attr(
                    out,
                    "type",
                    if kind == "submit" { "submit" } else { "button" },
                );
                match kind {
                    "button" => attr(out, "data-action", p("action")),
                    "open" => attr(out, "data-open-dialog", p("to")),
                    "close" => attr(out, "data-close-dialog", p("to")),
                    "back" => attr(out, "data-back", "true"),
                    "pick" => attr(out, "data-pick", "true"),
                    "navigate" => {
                        attr(out, "data-navigate", p("to"));
                        if let Some(action) = props.get("action") {
                            attr(out, "data-route-action", action);
                        }
                    }
                    _ => {}
                }
            }
            "value" => {
                let label = props.get("label").map_or(p("state"), String::as_str);
                write!(out, "><span>{}: </span><output data-state=\"{}\" aria-live=\"polite\"></output></div>", html(label), html(p("state"))).unwrap();
                return Ok(());
            }
            "select" => {
                attr(out, "data-choice", p("state"));
                write!(out, " id=\"sdr-field-{class}\">").unwrap();
                for child in &node.children {
                    self.node(child, page, out)?;
                }
                out.push_str("</select></div>");
                return Ok(());
            }
            "option" => attr(out, "value", p("value")),
            "input" => {
                // The layout properties belong to the field container.
                let key = html(p("state"));
                let field = format!("sdr-field-{class}");
                let attrs = format!("id=\"{field}\" data-input=\"{key}\" aria-describedby=\"{field}-error\" aria-invalid=\"false\"");
                match p("kind") {
                    "" | "textarea" => write!(out, "><textarea {attrs}></textarea>"),
                    "integer" => {
                        write!(out, "><input type=\"text\" inputmode=\"numeric\" {attrs}>")
                    }
                    kind => write!(out, "><input type=\"{kind}\" {attrs}>"),
                }
                .unwrap();
                write!(out, "<small id=\"{field}-error\" role=\"alert\" hidden>Value rejected by declared type or rules</small></div></div>").unwrap();
                return Ok(());
            }
            "checkbox" => {
                write!(
                    out,
                    "><label><input type=\"checkbox\" data-check=\"{}\">{}</label></div>",
                    html(p("state")),
                    html(p("label"))
                )
                .unwrap();
                return Ok(());
            }
            "when" => {
                attr(out, "data-when", p("state"));
                out.push_str(" hidden");
            }
            "form" => attr(out, "data-submit", p("action")),
            "dialog" => attr(out, "data-dialog", p("id")),
            "field" => attr(out, "data-row-field", p("field")),
            "row-when" => attr(out, "data-row-when", p("field")),
            "list" | "table" | "each" => {
                attr(
                    out,
                    if kind == "each" {
                        "data-each"
                    } else {
                        "data-list"
                    },
                    p("collection"),
                );
                attr(out, "data-select", p("select"));
                attr(
                    out,
                    "aria-label",
                    props.get("label").map_or(p("collection"), String::as_str),
                );
                for (key, data) in [
                    ("fields", "data-table"),
                    ("title", "data-title-field"),
                    ("status", "data-status-field"),
                    ("search", "data-query-search"),
                    ("sort", "data-query-sort"),
                    ("where", "data-query-where"),
                    ("equals", "data-query-equals"),
                    ("active", "data-query-active"),
                    ("empty", "data-query-empty"),
                ] {
                    if let Some(value) = props.get(key) {
                        attr(out, data, value);
                    }
                }
            }
            _ => unreachable!("validated WebApp widget"),
        }
        out.push('>');
        if kind == "each" {
            out.push_str("<template>");
        }
        out.push_str(&html(p("text")));
        for child in &node.children {
            self.node(child, page, out)?;
        }
        if kind == "each" {
            out.push_str("</template><div data-each-items role=\"list\"></div>");
        }
        write!(out, "</{tag}>").unwrap();
        Ok(())
    }
}

pub(super) fn generate(site: Site, root: Option<&Path>) -> Result<StaticSite> {
    let mut render = Render {
        assets: Assets::new(root),
        css: String::new(),
        count: 0,
        webapp: false,
    };
    let mut sheets = Vec::new();
    let mut licenses = Vec::new();
    let mut images = BTreeMap::new();
    for path in &site.settings.stylesheets {
        sheets.push(render.assets.stylesheet(path)?);
    }
    for path in &site.settings.licenses {
        licenses.push(render.assets.license(path)?);
    }
    licenses.sort();
    licenses.dedup();
    for (directive, path) in &site.settings.images {
        images.insert(directive.as_str(), render.assets.image(path)?);
    }

    let light = light_theme(&site.theme);
    let scheme = if light { "light" } else { "dark" };
    let mut files = BTreeMap::new();
    for page in &site.pages {
        let lang = &page.lang;
        let title = html(&page.title);
        let description = html(&page.description);
        let mut out = format!(
            r#"<!doctype html>
<html lang="{lang}">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="{scheme}"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'self'; font-src 'self'; img-src 'self' https:; base-uri 'none'; form-action 'none'">
<title>{title}</title><meta name="description" content="{description}">
"#
        );
        for (rel, target) in [("icon", "favicon.svg"), ("stylesheet", "site.css")]
            .into_iter()
            .chain(sheets.iter().map(|name| ("stylesheet", name.as_str())))
            .chain(licenses.iter().map(|name| ("license", name.as_str())))
            .chain(images.get("favicon").map(|name| ("icon", name.as_str())))
        {
            write!(
                out,
                "<link rel=\"{rel}\" href=\"{}\">",
                relative(target, page)
            )
            .unwrap();
        }
        if let Some(origin) = &site.settings.origin {
            let canonical = html(&format!("{origin}{}", page.route));
            write!(out, r#"<link rel="canonical" href="{canonical}"><meta property="og:url" content="{canonical}"><meta property="og:title" content="{title}"><meta property="og:description" content="{description}"><meta property="og:type" content="website">"#).unwrap();
            if let Some(image) = images.get("social-image") {
                write!(
                    out,
                    "<meta property=\"og:image\" content=\"{}\">",
                    html(&format!("{origin}/{image}"))
                )
                .unwrap();
            }
        }
        let skip = if lang.starts_with("ru") {
            "К содержимому"
        } else {
            "Skip to content"
        };
        write!(
            out,
            "</head><body><a class=\"s-skip\" href=\"#content\">{skip}</a>"
        )
        .unwrap();
        if let Some(nav) = page.nodes.first().filter(|n| n.kind == "navbar") {
            render.node(nav, page, &mut out)?;
        }
        out.push_str("<main id=\"content\" class=\"s-page\" tabindex=\"-1\">");
        for n in page
            .nodes
            .iter()
            .filter(|n| !matches!(n.kind.as_str(), "navbar" | "footer"))
        {
            render.node(n, page, &mut out)?;
        }
        out.push_str("</main>");
        if let Some(footer) = page.nodes.last().filter(|n| n.kind == "footer") {
            render.node(footer, page, &mut out)?;
        }
        out.push_str("</body></html>\n");
        files.insert(filename(&page.route), out.into_bytes());
    }
    let css = stylesheet(&site.theme, light, &render.css);
    let background = &site.theme["background"];
    files.insert("site.css".into(), css.into_bytes());
    let accent = &site.theme["accent"];
    let gold = &site.theme["gold"];
    files.insert("favicon.svg".into(), format!(r#"<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48"><rect width="48" height="48" rx="12" fill="{background}"/><path d="M24 7L40 24L24 41L8 24Z" fill="{accent}"/><circle cx="24" cy="24" r="5" fill="{gold}"/></svg>
"#).into_bytes());
    if let Some(origin) = &site.settings.origin {
        let mut sitemap = String::from(
            r#"<?xml version="1.0" encoding="utf-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">"#,
        );
        for page in &site.pages {
            write!(
                sitemap,
                "<url><loc>{}</loc></url>",
                html(&format!("{origin}{}", page.route))
            )
            .unwrap();
        }
        sitemap.push_str("</urlset>\n");
        let rule = if site.settings.robots.unwrap_or(true) {
            "Allow"
        } else {
            "Disallow"
        };
        files.insert("sitemap.xml".into(), sitemap.into_bytes());
        files.insert(
            "robots.txt".into(),
            format!("User-agent: *\n{rule}: /\nSitemap: {origin}/sitemap.xml\n").into_bytes(),
        );
    }
    files.extend(render.assets.files);
    Ok(StaticSite { files })
}

fn light_theme(theme: &Props) -> bool {
    let background = &theme["background"];
    let luminance: f64 = [0.2126, 0.7152, 0.0722]
        .into_iter()
        .enumerate()
        .map(|(i, weight)| {
            let v = f64::from(u8::from_str_radix(&background[1 + 2 * i..3 + 2 * i], 16).unwrap())
                / 255.0;
            weight
                * if v <= 0.04045 {
                    v / 12.92
                } else {
                    ((v + 0.055) / 1.055).powf(2.4)
                }
        })
        .sum();
    luminance > 0.179
}

fn stylesheet(theme: &Props, light: bool, node_styles: &str) -> String {
    let mut css = String::from(":root{");
    for (key, value) in theme {
        write!(css, "--{key}:{value};").unwrap();
    }
    css.push_str("}\n");
    if light {
        css.push_str(&CSS.replace("color-scheme:dark", "color-scheme:light")
            .replace("background:radial-gradient(ellipse at 12% 0%,#292039 0%,transparent 48rem),var(--background)", "background:var(--background)")
            .replace("background:linear-gradient(125deg,#302541,var(--surface))", "background:var(--surface)"));
    } else {
        css.push_str(CSS);
    }
    css.push('\n');
    css.push_str(node_styles);
    css
}

pub(super) fn webapp(
    title: &str,
    presentation: Site,
    palettes: &BTreeMap<String, Props>,
    views: &[super::webapp::View],
    script: String,
    root: Option<&Path>,
) -> Result<StaticSite> {
    let mut render = Render {
        assets: Assets::new(root),
        css: String::new(),
        count: 0,
        webapp: true,
    };
    let light = light_theme(&presentation.theme);
    let scheme = if light { "light" } else { "dark" };
    let mut out = format!(
        r#"<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="{scheme}"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'self'; style-src 'self'; font-src 'self'; img-src 'self' https:; base-uri 'none'; connect-src 'none'; form-action 'none'">
<title>{}</title><link rel="stylesheet" href="app.css"><script src="app.js" defer></script>"#,
        html(title)
    );
    for sheet in &presentation.settings.stylesheets {
        let name = render.assets.stylesheet(sheet)?;
        write!(out, "<link rel=\"stylesheet\" href=\"{name}\">").unwrap();
    }
    let mut licenses = std::collections::BTreeSet::new();
    for license in &presentation.settings.licenses {
        licenses.insert(render.assets.license(license)?);
    }
    for name in licenses {
        write!(out, "<link rel=\"license\" href=\"{name}\">").unwrap();
    }
    if let Some(icon) = presentation.settings.images.get("favicon") {
        let name = render.assets.image(icon)?;
        write!(out, "<link rel=\"icon\" href=\"{name}\">").unwrap();
    }
    out.push_str("</head><body><main id=\"content\" class=\"s-webapp\">");
    let root_page = Page {
        route: "/".into(),
        title: String::new(),
        description: String::new(),
        lang: "en".into(),
        nodes: Vec::new(),
        ids: Default::default(),
    };
    for view in views {
        write!(
            out,
            "<section data-view=\"{}\"{}>",
            view.name,
            if view.name == "main" { "" } else { " hidden" }
        )
        .unwrap();
        for node in &view.nodes {
            render.node(node, &root_page, &mut out)?;
        }
        out.push_str("</section>");
    }
    out.push_str("</main><p id=\"sedrava-error\" role=\"alert\" hidden></p></body></html>\n");
    let mut css = stylesheet(&presentation.theme, light, "");
    for (name, palette) in palettes {
        let scheme = if light_theme(palette) {
            "light"
        } else {
            "dark"
        };
        write!(css, ":root[data-theme=\"{name}\"]{{color-scheme:{scheme};").unwrap();
        for (key, value) in palette {
            write!(css, "--{key}:{value};").unwrap();
        }
        css.push_str("}\n");
    }
    css.push_str(include_str!("webapp.css"));
    css.push_str(&render.css);
    let mut files = render.assets.files;
    files.insert("index.html".into(), out.into_bytes());
    files.insert("app.css".into(), css.into_bytes());
    files.insert("app.js".into(), script.into_bytes());
    Ok(StaticSite { files })
}
