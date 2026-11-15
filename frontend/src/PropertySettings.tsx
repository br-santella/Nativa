import { useMemo, useState } from "react";
import type { ReactNode } from "react";
import type { Farm } from "./data";
import type { Area } from "./api";
import type { SetupInputs } from "./PropertyWizard";
import { PROBLEMS, commodities, hectares, soilFields, soilMax, square } from "./PropertyWizard";
import LocationMap from "./LocationMap";
import type { LatLon, MapFocus } from "./LocationMap";
import { locale, t, useLanguage } from "./i18n";
import { insideParana } from "./coverage";
import options from "./setup-options.json";

type Props = {
    farm: Farm;
    inputs?: SetupInputs;
    /** Dashboard priority sliders (0–100): water, soil, income, climate resilience. */
    weights: number[];
    savedAt: string | null;
    report: File | null;
    onReport: (file: File | null) => void;
    onSave: (farm: Farm, inputs: SetupInputs | undefined, weights: number[]) => void;
    onRedo: () => void;
    onForget: () => void;
};
type Mode = "demo" | "point" | "polygon";
type Place = { label: string; lat: number; lon: number };

const WEIGHT_LABELS = ["Economia de água", "Saúde do solo", "Rentabilidade", "Resiliência climática"];
/** Silt is only a helper for the wizard's texture fields; the engine does not receive it. */
const SOIL_FIELDS = soilFields.filter(([id]) => id !== "silte_pct");
const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);
const fixed = (n: number) => n.toFixed(6);

/** "dd/mm" (engine format) -> ISO date in the reference year, for a date input. */
function ddmmToIso(ddmm: string | undefined, reference: string): string {
    if (!ddmm) return "";
    const [day, month] = ddmm.split("/");
    return `${reference.slice(0, 4)}-${month}-${day}`;
}

/** How the saved area is edited: sample field, pin (~100 ha) or drawn boundary ([lon, lat] ring -> [lat, lon] corners). */
function areaState(inputs: SetupInputs | undefined, farm: Farm): { mode: Mode; demo: string; vertices: LatLon[]; pointHa: string } {
    const area = inputs?.area, demo = options.talhoes_demo[0].id;
    if (area && "talhao_id" in area) return { mode: "demo", demo: area.talhao_id, vertices: [], pointHa: "100" };
    if (area && "geometry" in area) {
        const ring = (area.geometry.coordinates[0] as [number, number][]).map(([lon, lat]) => [lat, lon] as LatLon);
        return { mode: "polygon", demo, vertices: ring.slice(0, -1), pointHa: "100" };
    }
    return { mode: "point", demo, vertices: [], pointHa: inputs ? "100" : farm.area };
}

function Row({ label, children }: { label: string; children: ReactNode }) {
    return (<div>
      <dt>{t(label)}</dt>
      <dd>{children}</dd>
    </div>);
}

function Select({ label, value, values, onChange }: { label: string; value: string; values: string[]; onChange: (v: string) => void }) {
    return (<Row label={label}>
      <select aria-label={t(label)} value={value} onChange={(e) => onChange(e.target.value)}>
        {values.map((v) => (<option key={v} value={v}>{t(v)}</option>))}
      </select>
    </Row>);
}

function YesNo({ label, value, onChange }: { label: string; value: boolean; onChange: (v: boolean) => void }) {
    return (<Row label={label}>
      <select aria-label={t(label)} value={value ? "yes" : "no"} onChange={(e) => onChange(e.target.value === "yes")}>
        <option value="yes">{t("Sim")}</option>
        <option value="no">{t("Não")}</option>
      </select>
    </Row>);
}

/** Settings view of the property and of everything entered in the setup; saving re-runs the engine with the new values. */
export default function PropertySettings({ farm, inputs, weights, savedAt, report, onReport, onSave, onRedo, onForget }: Props) {
    useLanguage();
    const initialArea = useMemo(() => areaState(inputs, farm), [inputs, farm]);
    const [draftFarm, setDraftFarm] = useState<Farm>(farm);
    const [draft, setDraft] = useState<SetupInputs | undefined>(inputs);
    const [draftWeights, setDraftWeights] = useState<number[]>(weights);
    const [mode, setMode] = useState<Mode>(initialArea.mode);
    const [demo, setDemo] = useState(initialArea.demo);
    const [vertices, setVertices] = useState<LatLon[]>(initialArea.vertices);
    const [pointHa, setPointHa] = useState(initialArea.pointHa);
    const [focus, setFocus] = useState<MapFocus | null>(null);
    const [cityQuery, setCityQuery] = useState(farm.city.replace(/,\s*PR$/i, ""));
    const [address, setAddress] = useState(farm.address ?? "");
    const [places, setPlaces] = useState<Place[]>([]);
    const [searching, setSearching] = useState(false), [searchNote, setSearchNote] = useState("");
    const [error, setError] = useState("");
    const set = (patch: Partial<SetupInputs>) => setDraft((v) => (v ? { ...v, ...patch } : v));
    const field = (key: keyof Farm, value: string) => setDraftFarm((f) => ({ ...f, [key]: value }));

    const sample = options.talhoes_demo.find((x) => x.id === demo)!;
    const sampleFocus = useMemo<MapFocus>(() => ({ lat: sample.lat, lon: sample.lon, zoom: 14, key: Number(sample.id) }), [sample]);
    const drawnHa = hectares(vertices);
    const markedPoints: LatLon[] = mode === "point"
        ? [[Number(draftFarm.latitude), Number(draftFarm.longitude)], ...(Number(pointHa) > 0 ? square(Number(draftFarm.latitude), Number(draftFarm.longitude), Number(pointHa)) : [])]
        : mode === "polygon" ? vertices : [];
    const outsideCoverage = markedPoints.some(([lat, lon]) => !insideParana(lat, lon));
    const areaChanged = !same({ mode, demo, vertices, pointHa }, initialArea);
    const dirty = areaChanged || !same(draftFarm, farm) || !same(draft, inputs) || !same(draftWeights, weights);
    const rotation = options.combinacoes.find((c) => c.id === draft?.rotacao_atual);
    const summer = options.culturas_verao.find((c) => c.id === rotation?.verao);

    /** Moves the map (and, when marking a point, the pin) to a city or an address. */
    function place(lat: number, lon: number, zoom: number) {
        setFocus({ lat, lon, zoom, key: Date.now() });
        if (mode === "point") setDraftFarm((f) => ({ ...f, latitude: fixed(lat), longitude: fixed(lon) }));
    }
    function pickCity(value: string) {
        setCityQuery(value);
        const city = options.municipios.find((x) => x.nome.toLocaleLowerCase("pt-BR") === value.trim().toLocaleLowerCase("pt-BR"));
        field("city", city ? `${city.nome}, PR` : value);
        if (city) place(city.lat, city.lon, 13);
    }
    async function searchAddress() {
        const query = address.trim();
        if (!query) return;
        setSearching(true); setSearchNote(""); setPlaces([]);
        const city = cityQuery.trim();
        const params = new URLSearchParams({ q: `${query}${city && !query.toLocaleLowerCase("pt-BR").includes(city.toLocaleLowerCase("pt-BR")) ? `, ${city}` : ""}, Paraná`, format: "jsonv2", limit: "5", countrycodes: "br", viewbox: "-54.7,-22.4,-47.9,-26.8", bounded: "1", "accept-language": locale() });
        try {
            const response = await fetch("https://nominatim.openstreetmap.org/search?" + params);
            if (!response.ok) throw Error(String(response.status));
            const found = (await response.json() as { display_name: string; lat: string; lon: string }[]).map((x) => ({ label: x.display_name, lat: Number(x.lat), lon: Number(x.lon) }));
            setPlaces(found);
            if (!found.length) setSearchNote(t("Não encontramos esse endereço no Paraná. Tente incluir a cidade ou marque direto no mapa."));
        } catch {
            setSearchNote(t("Não foi possível buscar o endereço agora. Marque direto no mapa ou informe as coordenadas."));
        } finally { setSearching(false); }
    }
    function choosePlace(found: Place) {
        setPlaces([]); setSearchNote("");
        field("address", found.label);
        place(found.lat, found.lon, 16);
    }
    function setSoil(id: string, value: string) {
        if (!draft) return;
        const soil = { ...draft.analise_solo };
        if (value === "") delete soil[id];
        else soil[id] = Number(value);
        set({ analise_solo: Object.keys(soil).length ? soil : undefined });
    }
    function setPrice(id: string, value: string) {
        if (!draft) return;
        const prices = { ...draft.ajustes?.precos };
        if (value === "") delete prices[id];
        else prices[id] = Number(value);
        set({ ajustes: Object.keys(prices).length ? { precos: prices } : undefined });
    }
    function setOptional(key: "estagio_verao" | "colheita_prevista" | "semeadura_safrinha", value: string) {
        setDraft((v) => {
            if (!v) return v;
            const next = { ...v };
            if (value) next[key] = value;
            else delete next[key];
            return next;
        });
    }

    /** Area sent to the engine plus the farm fields that describe it; throws a user-facing message when invalid. */
    function builtArea(): { area: Area; farm: Partial<Farm> } {
        if (mode === "demo")
            return { area: { talhao_id: demo }, farm: { latitude: String(sample.lat), longitude: String(sample.lon), area: String(sample.area_ha), city: `${sample.municipio}, PR` } };
        if (outsideCoverage) throw Error(t("Fora da área de cobertura: marque um ponto ou contorno dentro do Paraná."));
        if (mode === "point") {
            const ha = Number(pointHa), lat = Number(draftFarm.latitude), lon = Number(draftFarm.longitude);
            if (!(ha >= 1 && ha <= 10000)) throw Error(t("Informe o tamanho da área entre 1 e 10.000 ha."));
            // The engine turns a bare point into ~100 ha; any other size is sent as a square around the point.
            const corners = square(lat, lon, ha);
            const area: Area = ha === 100 ? { lat, lon } : { geometry: { type: "Polygon", coordinates: [[...corners, corners[0]].map(([a, b]) => [b, a])] } };
            return { area, farm: { area: pointHa } };
        }
        if (vertices.length < 3) throw Error(t("Marque pelo menos 3 cantos da sua área no mapa."));
        return {
            area: { geometry: { type: "Polygon", coordinates: [[...vertices, vertices[0]].map(([lat, lon]) => [lon, lat])] } },
            farm: { latitude: fixed(vertices.reduce((s, [lat]) => s + lat, 0) / vertices.length), longitude: fixed(vertices.reduce((s, [, lon]) => s + lon, 0) / vertices.length), area: drawnHa.toFixed(1) },
        };
    }

    function save() {
        setError("");
        try {
            if (!draftFarm.name.trim()) throw Error(t("Informe o nome da propriedade."));
            if (!draftWeights.some(Boolean)) throw Error(t("Defina pelo menos uma prioridade maior que zero."));
            const soil = draft?.analise_solo ?? {};
            if (("argila_pct" in soil) !== ("areia_pct" in soil)) throw Error(t("Para informar a textura, preencha argila e areia juntas."));
            if ((soil.argila_pct ?? 0) + (soil.areia_pct ?? 0) > 100) throw Error(t("Argila e areia devem somar no máximo 100%."));
            const built = builtArea();
            if (!draft) return onSave({ ...draftFarm, ...built.farm }, undefined, draftWeights);
            const [agua, solo, renda, risco] = draftWeights.map((w) => Math.round(w) / 10);
            // Keep the farm fields other pages read (irrigation, soil, crop) in step with the setup answers.
            const nextFarm: Farm = {
                ...draftFarm,
                ...built.farm,
                irrigation: draft.irrigacao.disponivel ? "Sim" : "Não",
                crop: draft.rotacao_atual.startsWith("soja__") ? "Soja" : "Milho",
                ...(soil.ph !== undefined ? { ph: String(soil.ph) } : {}),
                ...(soil.materia_organica_pct !== undefined ? { organic: String(soil.materia_organica_pct) } : {}),
            };
            onSave(nextFarm, { ...draft, area: built.area, pesos: { ...draft.pesos, agua, solo, renda, risco } }, draftWeights);
        } catch (e) {
            setError((e as Error).message);
        }
    }
    function discard() {
        setDraftFarm(farm);
        setDraft(inputs);
        setDraftWeights(weights);
        setMode(initialArea.mode); setDemo(initialArea.demo); setVertices(initialArea.vertices); setPointHa(initialArea.pointHa);
        setCityQuery(farm.city.replace(/,\s*PR$/i, "")); setAddress(farm.address ?? ""); setPlaces([]); setSearchNote("");
        setError("");
    }

    return (<section className="property-settings">
      <div className="section-heading">
        <div>
          <h2>{t("Minha Propriedade")}</h2>
          <p>{t(savedAt
            ? "Salvos neste navegador. É com eles que o motor calcula os seus cenários."
            : "Ainda não salvos: conclua o cadastro ou salve as alterações para guardá-los.")}
            {savedAt && <> {t("Último salvamento:")} {new Date(savedAt).toLocaleString(locale())}.</>}</p>
        </div>
      </div>

      <section className="panel settings-area">
        <h2>{t("Sua área")}</h2>
        <p className="coverage-notice" role="note">
          <strong>{t("Cobertura: somente Paraná (PR).")}</strong>{" "}
          {t("Os dados de solo, relevo, clima e custos usados nas recomendações foram preparados apenas para propriedades no estado.")}
        </p>
        <div className="settings-area-fields">
          <label className="field">
            <span>{t("Nome da propriedade")}</span>
            <input value={draftFarm.name} onChange={(e) => field("name", e.target.value)}/>
          </label>
          {draft && (<div className="wizard-segmented" role="radiogroup" aria-label={t("Como marcar sua área")}>
              {([["demo", "✦", "Talhão de exemplo"], ["point", "⌖", "Marcar um ponto"], ["polygon", "⬠", "Desenhar o contorno"]] as const).map(([id, icon, label]) => (<label key={id}>
                  <input type="radio" name="settings-mark-mode" checked={mode === id} onChange={() => setMode(id)}/>
                  <span><span aria-hidden="true">{icon}</span>{t(label)}</span>
                </label>))}
            </div>)}
        </div>

        {mode === "demo" ? (<div className="wizard-sample">
            <div className="wizard-sample-facts">
              <label className="field">
                <span>{t("Talhão")}</span>
                <select value={demo} onChange={(e) => setDemo(e.target.value)}>
                  {options.talhoes_demo.map((x) => (<option key={x.id} value={x.id}>{`${t("Talhão")} ${x.id} · ${x.municipio} · ${x.area_ha} ha`}</option>))}
                </select>
              </label>
              <div><dt>{t("Município")}</dt><dd>{sample.municipio}, PR</dd></div>
              <div><dt>{t("Área")}</dt><dd>{sample.area_ha} ha</dd></div>
              <div><dt>{t("Coordenadas")}</dt><dd>{sample.lat.toFixed(4)}, {sample.lon.toFixed(4)}</dd></div>
            </div>
            <LocationMap mode="view" latitude={String(sample.lat)} longitude={String(sample.lon)} focus={sampleFocus} zoom={14}/>
          </div>) : (<div className="settings-map">
            <div className="settings-finder">
              <label className="field">
                <span>{t("Cidade de referência")}</span>
                <input list="settings-cities" value={cityQuery} onChange={(e) => pickCity(e.target.value)} placeholder={t("Digite para buscar")} autoComplete="off"/>
                <datalist id="settings-cities">{options.municipios.map((x) => (<option key={x.id} value={x.nome}/>))}</datalist>
              </label>
              <label className="field">
                <span>{t("Endereço de referência")}</span>
                <span className="wizard-search">
                  <input value={address} onChange={(e) => setAddress(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); searchAddress(); } }} placeholder={t("Ex.: Linha Gaúcha, km 4")}/>
                  <button type="button" onClick={searchAddress} disabled={searching || !address.trim()}>{t(searching ? "Buscando…" : "Buscar")}</button>
                </span>
              </label>
            </div>
            {places.length > 0 && (<ul className="wizard-places" aria-label={t("Endereços encontrados")}>
                {places.map((x) => (<li key={`${x.lat},${x.lon}`}><button type="button" onClick={() => choosePlace(x)}>{x.label}</button></li>))}
              </ul>)}
            {searchNote && <p className="wizard-hint" role="status">{searchNote}</p>}
            <LocationMap mode={mode === "polygon" ? "polygon" : "point"} latitude={draftFarm.latitude} longitude={draftFarm.longitude} onChange={(latitude, longitude) => setDraftFarm((f) => ({ ...f, latitude, longitude }))} vertices={vertices} onVerticesChange={setVertices} focus={focus} pointHa={mode === "point" && Number(pointHa) > 0 ? Number(pointHa) : undefined}/>
            {mode === "point" && (<div className="settings-point">
                <label className="field"><span>{t("Latitude")}</span><input type="number" step="any" min={-27} max={-22} value={draftFarm.latitude} onChange={(e) => field("latitude", e.target.value)}/></label>
                <label className="field"><span>{t("Longitude")}</span><input type="number" step="any" min={-55} max={-48} value={draftFarm.longitude} onChange={(e) => field("longitude", e.target.value)}/></label>
                <label className="field"><span>{t("Tamanho da área (ha)")}</span><input type="number" min="1" max="10000" step="any" value={pointHa} onChange={(e) => setPointHa(e.target.value)}/></label>
              </div>)}
            {mode === "polygon" && (<div className="wizard-polygon-bar">
                <span role="status">{vertices.length < 3
                    ? `${vertices.length} ${t("de 3 cantos marcados")}`
                    : `${t("Contorno com")} ${vertices.length} ${t("cantos")} · ${t("cerca de")} ${drawnHa.toFixed(1)} ha`}</span>
                <span>
                  <button type="button" className="wizard-inline-link" disabled={!vertices.length} onClick={() => setVertices(vertices.slice(0, -1))}>{t("Desfazer último canto")}</button>
                  <button type="button" className="wizard-inline-link" disabled={!vertices.length} onClick={() => setVertices([])}>{t("Limpar")}</button>
                </span>
              </div>)}
            {outsideCoverage && <p className="wizard-error" role="alert">{t("Fora da área de cobertura: marque um ponto ou contorno dentro do Paraná.")}</p>}
          </div>)}
      </section>

      <div className="settings-grid">
        {draft ? (<section className="panel">
            <h2>{t("Sua lavoura")}</h2>
            <dl className="preferences">
              <Row label="Rotação atual">
                <select aria-label={t("Rotação atual")} value={draft.rotacao_atual} onChange={(e) => {
                    const next = options.combinacoes.find((c) => c.id === e.target.value);
                    setDraft((v) => {
                        if (!v) return v;
                        const out = { ...v, rotacao_atual: e.target.value };
                        // A crop stage only makes sense for the summer crop it was picked for.
                        if (next?.verao !== rotation?.verao) delete out.estagio_verao;
                        return out;
                    });
                }}>
                  {options.culturas_verao.map((crop) => (<optgroup key={crop.id} label={t(crop.nome)}>
                      {options.combinacoes.filter((c) => c.valida && c.verao === crop.id).map((c) => (<option key={c.id} value={c.id}>{t(c.nome)}</option>))}
                    </optgroup>))}
                </select>
              </Row>
              <Row label="Fase da cultura de verão">
                <select aria-label={t("Fase da cultura de verão")} value={draft.estagio_verao ?? ""} onChange={(e) => setOptional("estagio_verao", e.target.value)}>
                  <option value="">{t("Não sei informar")}</option>
                  {summer?.estagios.map((s) => (<option key={s.id} value={s.id}>{t(s.nome)}</option>))}
                </select>
              </Row>
              <Row label="Colheita prevista">
                <input aria-label={t("Colheita prevista")} type="date" value={ddmmToIso(draft.colheita_prevista, draft.data_referencia)} onChange={(e) => setOptional("colheita_prevista", e.target.value ? `${e.target.value.slice(8, 10)}/${e.target.value.slice(5, 7)}` : "")}/>
              </Row>
              <Row label="Semeadura da 2ª safra">
                <select aria-label={t("Semeadura da 2ª safra")} value={draft.semeadura_safrinha ?? ""} onChange={(e) => setOptional("semeadura_safrinha", e.target.value)}>
                  <option value="">{t("Automática")}</option>
                  {options.semeaduras.map((d) => (<option key={d} value={d}>{d}</option>))}
                </select>
              </Row>
              <Row label="Data de referência">
                <input aria-label={t("Data de referência")} type="date" required value={draft.data_referencia} onChange={(e) => e.target.value && set({ data_referencia: e.target.value })}/>
              </Row>
            </dl>
          </section>) : (<section className="panel">
            <h2>{t("Personalize o motor")}</h2>
            <p>{t("Conclua o cadastro para informar rotação, problemas da área, análise de solo e operação. Depois, tudo pode ser ajustado aqui.")}</p>
            <button type="button" className="text-link" onClick={onRedo}>{t("Fazer o cadastro →")}</button>
          </section>)}

        <section className="panel">
          <h2>{t("Solo e água")}</h2>
          <dl className="preferences">
            <Select label="Textura do solo" value={draftFarm.texture} values={["Argiloso", "Arenoso", "Franco", "Siltoso", "Não informado"]} onChange={(v) => field("texture", v)}/>
            <Select label="Drenagem" value={draftFarm.drainage} values={["Moderada", "Boa", "Baixa", "Não informado"]} onChange={(v) => field("drainage", v)}/>
            {draft
                ? <YesNo label="Irrigação" value={draft.irrigacao.disponivel} onChange={(v) => set({ irrigacao: { disponivel: v } })}/>
                : <Select label="Disponibilidade de irrigação" value={draftFarm.irrigation} values={["Sim", "Não", "Não informado"]} onChange={(v) => field("irrigation", v)}/>}
            <Select label="Tipo de irrigação" value={draftFarm.irrigationType} values={["Pivô central", "Gotejamento", "Aspersão", "Não se aplica", "Outro"]} onChange={(v) => field("irrigationType", v)}/>
            <Row label="Restrições de água">
              <input aria-label={t("Restrições de água")} value={draftFarm.waterRestriction} onChange={(e) => field("waterRestriction", e.target.value)}/>
            </Row>
          </dl>
        </section>

        <section className="panel settings-wide">
          <h2>{t("Prioridades")}</h2>
          <p>{t("O peso de cada objetivo na nota dos cenários.")}</p>
          <div className="sliders">
            {WEIGHT_LABELS.map((label, i) => (<label key={label}>
                <span>{t(label)}<strong>{draftWeights[i]}%</strong></span>
                <input type="range" min="0" max="100" step="10" value={draftWeights[i]} aria-label={t(label)} onChange={(e) => setDraftWeights((w) => w.map((v, n) => (n === i ? +e.target.value : v)))}/>
                <small>{t("Menor")}<span>{t("Maior")}</span></small>
              </label>))}
          </div>
        </section>

        {draft && (<>
          <section className="panel">
            <h2>{t("Problemas conhecidos")}</h2>
            <p>{t("Pragas, doenças ou problemas de solo que já apareceram na área.")}</p>
            <div className="settings-checks">
              {PROBLEMS.map(([id, label]) => (<label key={id}>
                  <input type="checkbox" checked={draft.problemas_area.includes(id)} onChange={() => set({ problemas_area: draft.problemas_area.includes(id) ? draft.problemas_area.filter((x) => x !== id) : [...draft.problemas_area, id] })}/>
                  {t(label)}
                </label>))}
            </div>
          </section>

          <section className="panel">
            <h2>{t("Operação")}</h2>
            <dl className="preferences">
              {commodities.filter(([id]) => id !== "soja").map(([id, label]) => (<YesNo key={id} label={`${t("Comprador para")} ${t(label).toLocaleLowerCase(locale())}`} value={!draft.restricoes.sem_comprador.includes(id)} onChange={(has) => set({ restricoes: { ...draft.restricoes, sem_comprador: has ? draft.restricoes.sem_comprador.filter((x) => x !== id) : [...draft.restricoes.sem_comprador, id] } })}/>))}
              <YesNo label="Plataforma de milho" value={draft.restricoes.maquinas.plataforma_milho} onChange={(v) => set({ restricoes: { ...draft.restricoes, maquinas: { ...draft.restricoes.maquinas, plataforma_milho: v } } })}/>
              <YesNo label="Semeadora de consórcio" value={draft.restricoes.maquinas.semeadora_consorcio} onChange={(v) => set({ restricoes: { ...draft.restricoes, maquinas: { ...draft.restricoes.maquinas, semeadora_consorcio: v } } })}/>
            </dl>
          </section>
        </>)}

        <section className="panel settings-wide">
          <h2>{t("Análise de solo")}</h2>
          {draft ? (<>
              <p>{t("Em branco, usamos dados públicos de solo quando disponíveis.")}</p>
              <div className="fields-grid settings-fields">
                {SOIL_FIELDS.map(([id, label]) => (<label key={id} className="field">
                    <span>{t(label)}</span>
                    <input type="number" step="any" min={id === "ph" ? 3 : 0} max={soilMax[id] ?? 100} value={draft.analise_solo?.[id] ?? ""} onChange={(e) => setSoil(id, e.target.value)}/>
                  </label>))}
              </div>
            </>) : (<div className="fields-grid settings-fields">
              <label className="field"><span>{t("pH")}</span><input type="number" min={0} max={14} step=".1" value={draftFarm.ph} onChange={(e) => field("ph", e.target.value)}/></label>
              <label className="field"><span>{t("Matéria orgânica (%)")}</span><input type="number" min={0} max={100} step=".1" value={draftFarm.organic} onChange={(e) => field("organic", e.target.value)}/></label>
            </div>)}
          <div className="settings-report">
            <div>
              <h3>{t(report ? report.name : "Nenhum laudo anexado")}</h3>
              <small>{t("Arquivo local • não enviado nem analisado automaticamente.")}</small>
            </div>
            <label className="button secondary upload">
              {t(report ? "Substituir laudo" : "Adicionar laudo")}
              <input type="file" accept=".pdf,.png,.jpg,.jpeg" onChange={(e) => onReport(e.target.files?.[0] ?? null)}/>
            </label>
            {report && <button className="text-link" type="button" onClick={() => onReport(null)}>{t("Remover arquivo")}</button>}
          </div>
        </section>

        {draft && (<section className="panel settings-wide">
            <h2>{t("Preços e cenários")}</h2>
            <p>{t("R$/saca. Em branco, usamos os preços de referência.")}</p>
            <div className="fields-grid settings-fields">
              {commodities.map(([id, label]) => (<label key={id} className="field">
                  <span>{t(label)}</span>
                  <input type="number" min="0" step="any" value={draft.ajustes?.precos[id] ?? ""} onChange={(e) => setPrice(id, e.target.value)}/>
                </label>))}
              <label className="field">
                <span>{t("Alternativas à sua rotação atual")}</span>
                <select value={draft.n_alternativas} onChange={(e) => set({ n_alternativas: Number(e.target.value) })}>
                  {[1, 2, 3, 4, 5, 6].map((n) => (<option key={n} value={n}>{n}</option>))}
                </select>
              </label>
            </div>
          </section>)}
      </div>

      <div className="settings-property-actions">
        <button type="button" className="text-link" onClick={onRedo}>{t("Refazer o cadastro do início →")}</button>
        {savedAt && (<button type="button" className="text-link danger-link" onClick={() => {
                if (confirm(t("Apagar os dados da propriedade salvos neste navegador?")))
                    onForget();
            }}>{t("Apagar dados salvos")}</button>)}
      </div>

      {(dirty || error) && (<div className="settings-savebar" role="region" aria-label={t("Alterações não salvas")}>
          <span role={error ? "alert" : "status"} className={error ? "error" : ""}>{error || t("Você tem alterações não salvas.")}</span>
          <div>
            <button type="button" className="button secondary" onClick={discard}>{t("Descartar")}</button>
            <button type="button" className="button" onClick={save} disabled={!dirty}>{t("Salvar e recalcular")}</button>
          </div>
        </div>)}
    </section>);
}
