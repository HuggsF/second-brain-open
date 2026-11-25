import pytest

from core.docs_registry import DocsRegistryError, docs_root, page_status, regras_aprovadas


CORPO = ("## Regra\nTexto.\n\n## Exemplos\n| # | Caso |\n|---|---|\n| 1 | a |\n| 2 | b |\n\n"
         "## Perguntas em aberto\nNenhuma.\n")


def _pagina(root, rel, status="aprovada", versao=2, areas=("Operações", "Atendimento"), avais=None, raw=None,
            corpo=CORPO, dono="{ area: Operações, pessoa: X }"):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    if raw is not None:
        p.write_text(raw, encoding="utf-8")
        return
    if avais is None:
        avais = [{"area": a, "versao": versao} for a in areas]
    lines = ["---", 'title: "T"', "id: portal.x", f"status: {status}", f"versao: {versao}", f"areas_aval: {list(areas)}"]
    if dono is not None:
        lines.append(f"dono: {dono}")
    lines.append("avais:" if avais else "avais: []")
    for a in avais:
        campos = {"area": a.get("area"), "pessoa": "X", "data": "2026-11-09", "versao": a.get("versao"),
                  "email": "area-solicitante@empresa.example", **{k: v for k, v in a.items() if k not in ("area", "versao")}}
        lines.append("  - { " + ", ".join(f"{k}: {v}" for k, v in campos.items() if v is not None) + " }")
    lines += ["---", "", corpo]
    p.write_text("\n".join(lines), encoding="utf-8")


R = "portal/regras/r.mdx"


def test_sem_variavel_a_raiz_e_a_pasta_de_fichas(tmp_path, monkeypatch):
    monkeypatch.setattr("config.settings.fichas_dir", tmp_path)
    assert docs_root({}) == tmp_path


def test_variavel_vazia_ou_so_espacos_vale_o_padrao(tmp_path, monkeypatch):
    monkeypatch.setattr("config.settings.fichas_dir", tmp_path)
    assert docs_root({"DOCS_REPO_PATH": ""}) == tmp_path
    assert docs_root({"DOCS_REPO_PATH": "   "}) == tmp_path


def test_pasta_de_fichas_inexistente_e_erro(tmp_path, monkeypatch):
    monkeypatch.setattr("config.settings.fichas_dir", tmp_path / "sem-fichas")
    with pytest.raises(DocsRegistryError, match="sem-fichas"):
        docs_root({})


def test_caminho_inexistente_recusa(tmp_path):
    alvo = tmp_path / "nao-existe"
    with pytest.raises(DocsRegistryError, match="nao-existe"):
        docs_root({"DOCS_REPO_PATH": str(alvo)})


def test_docs_root_valido(tmp_path):
    assert docs_root({"DOCS_REPO_PATH": str(tmp_path)}) == tmp_path


def test_pagina_ausente_recusa_citando_caminho(tmp_path):
    with pytest.raises(DocsRegistryError, match="regras/ausente.mdx"):
        page_status(tmp_path, "regras/ausente.mdx")


def test_frontmatter_malformado_cita_pagina(tmp_path):
    _pagina(tmp_path, "regras/ruim.mdx", raw="---\nstatus: [aberto\n---\n")
    with pytest.raises(DocsRegistryError, match="regras/ruim.mdx"):
        page_status(tmp_path, "regras/ruim.mdx")
    _pagina(tmp_path, "regras/sem.mdx", raw="sem frontmatter")
    with pytest.raises(DocsRegistryError, match="regras/sem.mdx"):
        page_status(tmp_path, "regras/sem.mdx")


def test_page_status_campos(tmp_path):
    _pagina(tmp_path, "r.mdx")
    s = page_status(tmp_path, "r.mdx")
    assert s["id"] == "portal.x" and s["status"] == "aprovada" and s["versao"] == 2 and len(s["avais"]) == 2


def test_regra_aprovada_com_aval_na_versao_passa(tmp_path):
    _pagina(tmp_path, R)
    assert regras_aprovadas(tmp_path, [R]) == []


def test_aval_de_versao_anterior_nao_conta(tmp_path):
    _pagina(tmp_path, R, avais=[{"area": "Operações", "versao": 2}, {"area": "Atendimento", "versao": 1}])
    assert regras_aprovadas(tmp_path, [R]) == [R]


def test_nao_aprovada_sem_areas_ou_versao_nao_inteira(tmp_path):
    rels = [f"portal/regras/{n}.mdx" for n in "abcd"]
    _pagina(tmp_path, rels[0], status="validada")
    _pagina(tmp_path, rels[1], areas=(), avais=[])
    _pagina(tmp_path, rels[2], versao="'2'", avais=[{"area": "Operações", "versao": "'2'"}, {"area": "Atendimento", "versao": "'2'"}])
    _pagina(tmp_path, rels[3], versao="true", avais=[{"area": "Operações", "versao": "true"}, {"area": "Atendimento", "versao": "true"}])
    assert regras_aprovadas(tmp_path, rels) == rels


# -- formato da página de regra ----------------------------------------

def test_versao_zero_nao_aprova(tmp_path):
    _pagina(tmp_path, R, versao=0)
    assert regras_aprovadas(tmp_path, [R]) == [R]


def test_versao_decimal_nao_aprova(tmp_path):
    _pagina(tmp_path, R, versao=1.5)
    assert regras_aprovadas(tmp_path, [R]) == [R]


def test_versao_1_ponto_0_aprova_como_no_js(tmp_path):
    # YAML 1.0 e inteiro em JS (Number.isInteger(1.0)); o aval pode vir como 1 ou 1.0
    _pagina(tmp_path, R, versao="1.0",
            avais=[{"area": "Operações", "versao": 1}, {"area": "Atendimento", "versao": "1.0"}])
    assert regras_aprovadas(tmp_path, [R]) == []


@pytest.mark.parametrize("invalido", [
    {"area": "Juridico", "versao": 0},
    {"area": "Juridico", "versao": "'2'"},
    {"area": "Juridico", "versao": 2, "email": "''"},
    {"area": "Juridico", "versao": 2, "pessoa": "''"},
    {"area": "Juridico", "versao": 2, "data": "''"},
    {"area": "''", "versao": 2},
])
def test_aval_invalido_ao_lado_dos_validos_nao_aprova(tmp_path, invalido):
    _pagina(tmp_path, R, avais=[{"area": "Operações", "versao": 2}, {"area": "Atendimento", "versao": 2}, invalido])
    assert regras_aprovadas(tmp_path, [R]) == [R]


def test_aval_que_nao_e_mapa_nao_aprova(tmp_path):
    _pagina(tmp_path, R, raw=(
        "---\ntitle: T\nid: portal.x\ndono: { area: C, pessoa: X }\nstatus: aprovada\nversao: 1\n"
        "areas_aval: [C]\navais:\n  - { area: C, pessoa: X, data: 2026-11-09, versao: 1, email: area-solicitante@empresa.example }\n"
        "  - texto solto\n---\n" + CORPO))
    assert regras_aprovadas(tmp_path, [R]) == [R]


def test_pagina_crua_valida_aprova(tmp_path):
    _pagina(tmp_path, R, raw=(
        "---\ntitle: T\nid: portal.x\ndono: { area: C, pessoa: X }\nstatus: aprovada\nversao: 1\n"
        "areas_aval: [C]\navais:\n  - { area: C, pessoa: X, data: 2026-11-09, versao: 1, email: area-solicitante@empresa.example }\n"
        "---\n" + CORPO))
    assert regras_aprovadas(tmp_path, [R]) == []


def test_um_exemplo_so_nao_aprova(tmp_path):
    corpo = "## Exemplos\n| # | Caso |\n|---|---|\n| 1 | a |\n\n## Perguntas em aberto\nNenhuma.\n"
    _pagina(tmp_path, R, corpo=corpo)
    assert regras_aprovadas(tmp_path, [R]) == [R]


@pytest.mark.parametrize("item", ["- Quem decide o prazo?", "* prazo?", "1. prazo?"])
def test_pergunta_em_aberto_nao_aprova(tmp_path, item):
    _pagina(tmp_path, R, corpo=CORPO.replace("Nenhuma.", item))
    assert regras_aprovadas(tmp_path, [R]) == [R]


def test_sem_dono_nao_aprova(tmp_path):
    _pagina(tmp_path, R, dono=None)
    assert regras_aprovadas(tmp_path, [R]) == [R]


def test_id_fora_do_padrao_nao_aprova(tmp_path):
    _pagina(tmp_path, R)
    p = tmp_path / R
    p.write_text(p.read_text(encoding="utf-8").replace("id: portal.x", "id: Regua_X"), encoding="utf-8")
    assert regras_aprovadas(tmp_path, [R]) == [R]


@pytest.mark.parametrize("rel", ["regras/r.mdx", "portal/r.mdx", "portal/regras/sub/r.mdx", "portal/regras/r.md"])
def test_regra_fora_de_produto_regras_nao_aprova(tmp_path, rel):
    _pagina(tmp_path, rel)
    assert regras_aprovadas(tmp_path, [rel]) == [rel]


# -- T7: caminho fora do repositorio e erro de leitura ----------------------------

@pytest.mark.parametrize("rel", ["../fora.mdx", "portal/../../fora.mdx"])
def test_caminho_relativo_fora_da_raiz_recusa(tmp_path, rel):
    root = tmp_path / "docs"
    root.mkdir()
    _pagina(tmp_path, "fora.mdx")
    with pytest.raises(DocsRegistryError, match="caminho fora do repositório de documentação: "):
        page_status(root, rel)


def test_caminho_absoluto_fora_da_raiz_recusa(tmp_path):
    root = tmp_path / "docs"
    root.mkdir()
    _pagina(tmp_path, "fora.mdx")
    fora = str(tmp_path / "fora.mdx")
    with pytest.raises(DocsRegistryError, match="caminho fora do repositório de documentação"):
        page_status(root, fora)
    assert regras_aprovadas(root, [fora]) == [fora]


def test_pagina_com_bytes_invalidos_recusa_citando_a_pagina(tmp_path):
    (tmp_path / "portal/regras").mkdir(parents=True)
    (tmp_path / R).write_bytes(b"---\nstatus: \xff\n---\n")
    with pytest.raises(DocsRegistryError, match="portal/regras/r.mdx"):
        page_status(tmp_path, R)


def test_erro_de_leitura_recusa_citando_a_pagina(tmp_path, monkeypatch):
    from pathlib import Path
    _pagina(tmp_path, R)

    def falha(self, *a, **k):
        raise PermissionError("negado")

    monkeypatch.setattr(Path, "read_text", falha)
    with pytest.raises(DocsRegistryError, match="portal/regras/r.mdx"):
        page_status(tmp_path, R)
