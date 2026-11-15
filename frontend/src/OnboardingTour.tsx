import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { t } from "./i18n";
import "./onboarding-tour.css";

/**
 * One stop of the guided tour. When the target is hidden, `fallback` is highlighted instead
 * (the menu button stands in for sidebar items on phones); with neither visible the card is centred.
 */
type Step = { target?: string; fallback?: string; title: string; body: string };
const MENU = ".mobile-menu";

const STEPS: Step[] = [
    {
        title: "Bem-vindo à NATIVA",
        body: "Em menos de um minuto, mostramos onde fica cada parte da plataforma. Você pode pular agora e rever este tutorial depois, no botão Ajuda.",
    },
    {
        target: ".property-select",
        title: "Sua propriedade",
        body: "Aqui aparece a propriedade que você cadastrou. Clique para ver os detalhes ou editar os dados dela.",
    },
    {
        target: ".overview-map",
        title: "Mapa e indicadores",
        body: "O mapa mostra a área da propriedade com camadas de satélite. Ao lado, os indicadores de clima, umidade e vegetação vêm de dados da NASA.",
    },
    {
        target: ".season-overview",
        title: "Sua safra atual",
        body: "Veja a rotação que você pratica hoje, em que fase está a lavoura e onde há espaço para melhorar o próximo ciclo.",
    },
    {
        target: '[data-tour="rotation"]',
        fallback: MENU,
        title: "Estratégias de Rotação",
        body: "O coração da NATIVA: compare alternativas para a próxima safra e ajuste o peso de água, solo, renda e risco climático.",
    },
    {
        target: '[data-tour="climate"]',
        fallback: MENU,
        title: "Análise Climática",
        body: "Chuva, temperatura e umidade do solo ao longo dos anos, para entender o clima da sua região.",
    },
    {
        target: '[data-tour="history"]',
        fallback: MENU,
        title: "Histórico de Cultivo",
        body: "Registre o que foi plantado em cada safra. Quanto mais completo o histórico, melhores as recomendações.",
    },
    {
        target: '[data-tour="settings"]',
        fallback: MENU,
        title: "Configurações",
        body: "Edite a propriedade, as respostas do cadastro e as preferências, como a unidade de temperatura.",
    },
    {
        target: '[data-tour="help"]',
        fallback: MENU,
        title: "Ajuda",
        body: "Dúvidas? Abra a Ajuda para ver o roteiro da plataforma e rever este tutorial quando quiser.",
    },
    {
        title: "Tudo pronto!",
        body: "Um bom primeiro passo é comparar as estratégias de rotação para a sua próxima safra.",
    },
];

const DONE_KEY = "nativa-tour-done-v1";
const PAD = 8;

/** True when the user has already finished or skipped the tour in this browser. */
export function tourSeen(): boolean {
    try {
        return localStorage.getItem(DONE_KEY) === "1";
    } catch {
        return false;
    }
}

function markSeen() {
    try {
        localStorage.setItem(DONE_KEY, "1");
    } catch {
        /* Storage is optional: the tour simply shows again next visit. */
    }
}

/** Visible box of the step target, or null when it does not exist or is off screen (e.g. the mobile sidebar). */
function targetRect(selector?: string): DOMRect | null {
    if (!selector) return null;
    const element = document.querySelector(selector);
    if (!element) return null;
    const rect = element.getBoundingClientRect();
    if (rect.width < 2 || rect.height < 2 || rect.right <= 0 || rect.left >= window.innerWidth) return null;
    return rect;
}

export default function OnboardingTour({ onClose, onFinish }: { onClose: () => void; onFinish: () => void }) {
    const [index, setIndex] = useState(0);
    const [rect, setRect] = useState<DOMRect | null>(null);
    const [cardSize, setCardSize] = useState({ width: 360, height: 220 });
    const card = useRef<HTMLDivElement>(null);
    const step = STEPS[index];
    const last = index === STEPS.length - 1;

    const close = useCallback((finished: boolean) => {
        markSeen();
        if (finished) onFinish();
        else onClose();
    }, [onClose, onFinish]);

    // Bring the target into view, then follow it on scroll/resize.
    useLayoutEffect(() => {
        const selector = targetRect(step.target) ? step.target : step.fallback;
        const element = selector ? document.querySelector(selector) : null;
        const initial = targetRect(selector);
        if (element && initial && (initial.top < 0 || initial.bottom > window.innerHeight))
            element.scrollIntoView({ block: "center", behavior: "instant" as ScrollBehavior });
        const update = () => setRect(targetRect(step.target) ?? targetRect(step.fallback));
        update();
        window.addEventListener("resize", update);
        window.addEventListener("scroll", update, true);
        return () => {
            window.removeEventListener("resize", update);
            window.removeEventListener("scroll", update, true);
        };
    }, [step.target, step.fallback]);

    useLayoutEffect(() => {
        const box = card.current?.getBoundingClientRect();
        if (box) setCardSize({ width: box.width, height: box.height });
        card.current?.focus();
    }, [index]);

    useEffect(() => {
        const onKey = (event: KeyboardEvent) => {
            if (event.key === "Escape") close(false);
            else if (event.key === "ArrowRight" && !last) setIndex(i => i + 1);
            else if (event.key === "ArrowLeft" && index > 0) setIndex(i => i - 1);
        };
        window.addEventListener("keydown", onKey);
        return () => window.removeEventListener("keydown", onKey);
    }, [close, index, last]);

    // Narrow targets on the left (sidebar items) get the card on their right; others get it below, or above,
    // or overlapping as a last resort. The card always stays inside the viewport.
    let position: React.CSSProperties = {};
    if (rect) {
        const gap = 14 + PAD, margin = 16;
        const vw = window.innerWidth, vh = window.innerHeight;
        const clamp = (value: number, max: number) => Math.min(Math.max(value, margin), max - margin);
        let top: number, left: number;
        if (rect.width < 320 && rect.right + gap + cardSize.width <= vw - margin) {
            left = rect.right + gap;
            top = rect.top + rect.height / 2 - cardSize.height / 2;
        } else {
            left = rect.left;
            if (rect.bottom + gap + cardSize.height <= vh - margin) top = rect.bottom + gap;
            else if (rect.top - gap - cardSize.height >= margin) top = rect.top - gap - cardSize.height;
            else top = vh - margin - cardSize.height;
        }
        position = { top: clamp(top, vh - cardSize.height), left: clamp(left, vw - cardSize.width) };
    }

    return (<div className="tour" role="dialog" aria-modal="true" aria-labelledby="tour-title" aria-describedby="tour-body">
      {rect
            ? <div className="tour-spotlight" style={{ top: rect.top - PAD, left: rect.left - PAD, width: rect.width + PAD * 2, height: rect.height + PAD * 2 }}/>
            : <div className="tour-shade"/>}
      <div ref={card} tabIndex={-1} className={"tour-card" + (rect ? "" : " centered")} style={position}>
        <span className="tour-progress">{t("Passo")} {index + 1} {t("de")} {STEPS.length}</span>
        <h2 id="tour-title">{t(step.title)}</h2>
        <p id="tour-body">{t(step.body)}</p>
        <div className="tour-dots" aria-hidden="true">
          {STEPS.map((_, i) => <span key={i} className={i === index ? "active" : ""}/>)}
        </div>
        <div className="tour-actions">
          {last
                ? <span />
                : <button type="button" className="tour-skip" onClick={() => close(false)}>{t("Pular tutorial")}</button>}
          <div>
            {index > 0 && <button type="button" className="button secondary" onClick={() => setIndex(i => i - 1)}>{t("Voltar")}</button>}
            {last
                ? <button type="button" className="button lime" onClick={() => close(true)}>{t("Comparar estratégias →")}</button>
                : <button type="button" className="button lime" onClick={() => setIndex(i => i + 1)}>{t(index === 0 ? "Começar" : "Próximo")}</button>}
          </div>
        </div>
        {last && <button type="button" className="tour-skip tour-later" onClick={() => close(false)}>{t("Explorar por conta própria")}</button>}
      </div>
    </div>);
}
