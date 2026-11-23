"""Ficha de projeto: validação da pasta, criação por modelos e comandos."""
import re
import shutil
import tempfile
import unittest
from datetime import date
from pathlib import Path

import yaml

from core import ficha

ROOT = Path(__file__).resolve().parent.parent
_FRENTE = re.compile(r"\A---\n(.*?)\n---\n(.*)\Z", re.S)

CORPOS = {
    1: "# Visão\n\nProblema, apetite e solução.\n",
    2: "# Especificação\n\nRequisitos.\n",
    3: "# Arquitetura\n\n```mermaid\nflowchart LR\n  a --> b\n```\n",
    5: "# Prontidão\n",
    7: "# Operação\n",
    9: "# Privacidade\n",
    10: "# Execução\n",
}
ORIGEM = "padrão de teste"


def gravar(caminho: Path, dados: dict, corpo: str = "# Título\n\nTexto.\n") -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text("---\n" + yaml.safe_dump(dados, allow_unicode=True, sort_keys=False) + "---\n" + corpo, encoding="utf-8")


def ler(caminho: Path):
    achado = _FRENTE.match(caminho.read_text(encoding="utf-8"))
    return yaml.safe_load(achado.group(1)), achado.group(2)


def trocar(caminho: Path, corpo=None, remover=(), **campos) -> None:
    dados, atual = ler(caminho)
    dados.update(campos)
    for chave in remover:
        dados.pop(chave, None)
    gravar(caminho, dados, atual if corpo is None else corpo)


def secao(numero: int) -> dict:
    return {"secao": numero, "origem": ORIGEM, "aplica": "sim"}


def escrever_ficha(raiz: Path, slug: str = "demo", porte: str = "medio") -> Path:
    pasta = raiz / "fichas" / slug
    (raiz / "provas").mkdir(parents=True, exist_ok=True)
    (raiz / "provas" / "saida.txt").write_text("ok\n", encoding="utf-8")
    gravar(pasta / "ficha.md", {"slug": slug, "nome": "Demo", "porte": porte, "estado": "ativo",
                                "repositorio": "https://example.org/demo", "data": "2026-11-23", "origem": ORIGEM})
    for numero in ficha.OBRIGATORIAS[porte]:
        alvo = pasta / ficha.ARQUIVOS[numero]
        if numero == 0:
            continue
        if numero == 4:
            gravar(alvo / "_secao.md", secao(4))
            gravar(alvo / "ADR-001-exemplo.md", {"id": "ADR-001", "status": "aceito", "data": "2026-11-01"},
                   "# Exemplo\n\n## Contexto\n\nA.\n\n## Opções consideradas\n\nB e C.\n\n## Decisão\n\nB.\n\n## Consequências\n\nD.\n")
        elif numero == 5:
            dados = secao(5)
            dados["categorias"] = {c: {"motivo": "não se aplica a um exemplo"} for c in ficha.CATEGORIAS_PRONTIDAO}
            gravar(alvo, dados, CORPOS[5])
        elif numero == 6:
            gravar(alvo / "_secao.md", secao(6))
            gravar(alvo / "2026-11-10-construcao.md", auditoria())
        elif numero == 8:
            gravar(alvo / "_secao.md", secao(8))
            gravar(alvo / "runbook-subir.md", {"tipo": "runbook", "dono": "mantenedor", "revisado_em": "2026-11-10"})
        else:
            gravar(alvo, secao(numero), CORPOS[numero])
    return pasta


def auditoria(**campos) -> dict:
    base = {"etapa": "construcao", "data": "2026-11-10", "veredito": "verde",
            "criterio": "a suíte passa", "evidencia": "provas/saida.txt"}
    base.update(campos)
    return base


class TestFicha(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.raiz = Path(tmp.name)

    def ficha(self, porte="medio"):
        return escrever_ficha(self.raiz, porte=porte)

    def validar(self, pasta):
        return ficha.validar(pasta, self.raiz)

    def problemas(self, pasta, numero=None):
        r = self.validar(pasta)
        self.assertFalse(r.valida)
        if numero is None:
            return r.problemas + [p for s in r.secoes for p in s.problemas]
        return [p for s in r.secoes if s.numero == numero for p in s.problemas]

    def assertProblema(self, pasta, numero, trecho):
        achados = self.problemas(pasta, numero)
        self.assertTrue(any(trecho in p for p in achados), f"esperava '{trecho}' em {achados}")

    # --- fichas válidas ---

    def test_ficha_pequena_valida(self):
        r = self.validar(self.ficha("pequeno"))
        self.assertTrue(r.valida, [s.problemas for s in r.secoes])
        self.assertEqual(r.situacao, "sem auditoria")
        self.assertEqual([s.numero for s in r.secoes], [0, 1, 3, 4])

    def test_ficha_media_valida(self):
        r = self.validar(self.ficha())
        self.assertTrue(r.valida, [s.problemas for s in r.secoes])
        self.assertEqual(r.situacao, "verde")

    def test_ficha_grande_valida(self):
        r = self.validar(self.ficha("grande"))
        self.assertTrue(r.valida, [s.problemas for s in r.secoes])
        self.assertEqual(len(r.secoes), 11)

    # --- seção 0 ---

    def test_campo_obrigatorio_ausente_em_ficha_md(self):
        pasta = self.ficha()
        trocar(pasta / "ficha.md", remover=("repositorio",))
        self.assertProblema(pasta, 0, "repositorio")

    def test_porte_fora_da_lista(self):
        pasta = self.ficha()
        trocar(pasta / "ficha.md", porte="enorme")
        self.assertProblema(pasta, 0, "porte")

    def test_estado_fora_da_lista(self):
        pasta = self.ficha()
        trocar(pasta / "ficha.md", estado="verde")
        self.assertProblema(pasta, 0, "estado")

    def test_slug_diferente_da_pasta(self):
        pasta = self.ficha()
        trocar(pasta / "ficha.md", slug="outro")
        self.assertProblema(pasta, 0, "slug")

    def test_pasta_sem_ficha_md(self):
        pasta = self.raiz / "fichas" / "vazia"
        pasta.mkdir(parents=True)
        r = self.validar(pasta)
        self.assertFalse(r.valida)
        self.assertTrue(any("ficha.md" in p for p in r.problemas))

    # --- regras comuns ---

    def test_secao_obrigatoria_ausente(self):
        pasta = self.ficha()
        (pasta / "05-prontidao.md").unlink()
        self.assertProblema(pasta, 5, "obrigatória")

    def test_secao_opcional_ausente_nao_aparece(self):
        r = self.validar(self.ficha("pequeno"))
        self.assertNotIn(7, [s.numero for s in r.secoes])

    def test_secao_opcional_presente_e_validada(self):
        pasta = self.ficha("pequeno")
        gravar(pasta / "07-operacao.md", {"secao": 7, "aplica": "sim"}, CORPOS[7])
        self.assertProblema(pasta, 7, "origem")

    def test_numero_da_secao_diferente_do_arquivo(self):
        pasta = self.ficha()
        trocar(pasta / "01-visao.md", secao=2)
        self.assertProblema(pasta, 1, "secao")

    def test_marcador_de_modelo_nao_preenchido(self):
        pasta = self.ficha()
        trocar(pasta / "01-visao.md", corpo="# Visão\n\n" + ficha.MARCADOR + "\n")
        self.assertProblema(pasta, 1, "preench")

    def test_marcador_em_item_de_pasta(self):
        pasta = self.ficha()
        trocar(pasta / "04-decisoes" / "ADR-001-exemplo.md", corpo="## Opções consideradas\n\n" + ficha.MARCADOR + "\n")
        self.assertProblema(pasta, 4, "preench")

    def test_nao_se_aplica_sem_motivo(self):
        pasta = self.ficha()
        trocar(pasta / "02-especificacao.md", aplica="nao")
        self.assertProblema(pasta, 2, "motivo")

    def test_nao_se_aplica_com_motivo(self):
        pasta = self.ficha()
        trocar(pasta / "08-processos" / "_secao.md", aplica="nao", motivo="projeto de uma pessoa, sem rotina")
        (pasta / "08-processos" / "runbook-subir.md").unlink()
        r = self.validar(pasta)
        self.assertTrue(r.valida, [s.problemas for s in r.secoes])
        self.assertEqual([s.situacao for s in r.secoes if s.numero == 8], ["nao_se_aplica"])

    def test_aplica_fora_da_lista(self):
        pasta = self.ficha()
        trocar(pasta / "01-visao.md", aplica="talvez")
        self.assertProblema(pasta, 1, "aplica")

    # --- seção 3 ---

    def test_arquitetura_sem_mermaid(self):
        pasta = self.ficha()
        trocar(pasta / "03-arquitetura.md", corpo="# Arquitetura\n\nSó texto.\n")
        self.assertProblema(pasta, 3, "mermaid")

    # --- seção 4 ---

    def test_decisoes_sem_adr(self):
        pasta = self.ficha()
        (pasta / "04-decisoes" / "ADR-001-exemplo.md").unlink()
        self.assertProblema(pasta, 4, "ADR")

    def test_adr_sem_opcoes_consideradas(self):
        pasta = self.ficha()
        trocar(pasta / "04-decisoes" / "ADR-001-exemplo.md", corpo="## Contexto\n\nA.\n\n## Decisão\n\nB.\n")
        self.assertProblema(pasta, 4, "Opções consideradas")

    def test_adr_status_fora_da_lista(self):
        pasta = self.ficha()
        trocar(pasta / "04-decisoes" / "ADR-001-exemplo.md", status="talvez")
        self.assertProblema(pasta, 4, "status")

    def test_adr_externo_dispensa_corpo(self):
        pasta = self.ficha()
        trocar(pasta / "04-decisoes" / "ADR-001-exemplo.md", corpo="", externo="https://example.org/adr/001.md")
        self.assertTrue(self.validar(pasta).valida)

    def test_adr_externo_que_nao_e_url(self):
        pasta = self.ficha()
        trocar(pasta / "04-decisoes" / "ADR-001-exemplo.md", corpo="", externo="docs/adr/001.md")
        self.assertProblema(pasta, 4, "externo")

    # --- seção 5 ---

    def test_prontidao_categoria_sem_evidencia_nem_motivo(self):
        pasta = self.ficha()
        dados, _ = ler(pasta / "05-prontidao.md")
        dados["categorias"]["seguranca"] = {}
        gravar(pasta / "05-prontidao.md", dados, CORPOS[5])
        self.assertProblema(pasta, 5, "seguranca")

    def test_prontidao_faltando_categoria(self):
        pasta = self.ficha()
        dados, _ = ler(pasta / "05-prontidao.md")
        del dados["categorias"]["volume"]
        gravar(pasta / "05-prontidao.md", dados, CORPOS[5])
        self.assertProblema(pasta, 5, "volume")

    def test_prontidao_evidencia_inexistente(self):
        pasta = self.ficha()
        dados, _ = ler(pasta / "05-prontidao.md")
        dados["categorias"]["seguranca"] = {"evidencia": "provas/nao-existe.txt"}
        gravar(pasta / "05-prontidao.md", dados, CORPOS[5])
        self.assertProblema(pasta, 5, "seguranca")

    # --- seção 6 ---

    def aud(self, pasta):
        return pasta / "06-auditorias" / "2026-11-10-construcao.md"

    def test_auditorias_sem_item(self):
        pasta = self.ficha()
        self.aud(pasta).unlink()
        self.assertProblema(pasta, 6, "auditoria")

    def test_auditoria_sem_evidencia(self):
        pasta = self.ficha()
        trocar(self.aud(pasta), remover=("evidencia",))
        self.assertProblema(pasta, 6, "evidencia")

    def test_auditoria_ambar_sem_pendencia_prazo_dono(self):
        pasta = self.ficha()
        trocar(self.aud(pasta), veredito="ambar")
        achados = " ".join(self.problemas(pasta, 6))
        for campo in ("pendencia", "prazo", "dono"):
            self.assertIn(campo, achados)

    def test_auditoria_ambar_completa_e_valida(self):
        pasta = self.ficha()
        trocar(self.aud(pasta), veredito="ambar", pendencia="corrigir testes", prazo="2026-12-15", dono="mantenedor")
        r = self.validar(pasta)
        self.assertTrue(r.valida, [s.problemas for s in r.secoes])
        self.assertEqual(r.situacao, "ambar")

    def test_auditoria_etapa_fora_da_lista(self):
        pasta = self.ficha()
        trocar(self.aud(pasta), etapa="homologacao")
        self.assertProblema(pasta, 6, "etapa")

    def test_auditoria_veredito_fora_da_lista(self):
        pasta = self.ficha()
        trocar(self.aud(pasta), veredito="azul")
        self.assertProblema(pasta, 6, "veredito")

    def test_evidencia_caminho_inexistente(self):
        pasta = self.ficha()
        trocar(self.aud(pasta), evidencia="provas/nao-existe.txt")
        self.assertProblema(pasta, 6, "evidencia")

    def test_evidencia_fora_da_raiz(self):
        pasta = self.ficha()
        fora = self.raiz.parent / (self.raiz.name + "-fora.txt")
        fora.write_text("x", encoding="utf-8")
        self.addCleanup(fora.unlink)
        for valor in ("../" + fora.name, str(fora)):
            trocar(self.aud(pasta), evidencia=valor)
            self.assertProblema(pasta, 6, "fora")

    def test_evidencia_url_nao_e_conferida(self):
        pasta = self.ficha()
        trocar(self.aud(pasta), evidencia="https://example.invalid/saida.txt")
        self.assertTrue(self.validar(pasta).valida)

    def test_situacao_usa_a_auditoria_mais_recente_por_etapa(self):
        pasta = self.ficha()
        pendente = {"pendencia": "p", "prazo": "2026-12-01", "dono": "mantenedor"}
        gravar(pasta / "06-auditorias" / "2026-11-01-construcao.md", auditoria(data="2026-11-01", veredito="vermelho", **pendente))
        gravar(pasta / "06-auditorias" / "2026-11-05-desenho.md", auditoria(etapa="desenho", data="2026-11-05", veredito="ambar", **pendente))
        r = self.validar(pasta)
        self.assertTrue(r.valida, [s.problemas for s in r.secoes])
        self.assertEqual(r.situacao, "ambar")

    def test_duas_auditorias_no_mesmo_dia_vale_a_de_nome_posterior(self):
        pasta = self.ficha()
        trocar(self.aud(pasta), veredito="ambar", pendencia="p", prazo="2026-12-01", dono="mantenedor")
        gravar(pasta / "06-auditorias" / "2026-11-10b-construcao.md", auditoria())
        r = self.validar(pasta)
        self.assertTrue(r.valida, [s.problemas for s in r.secoes])
        self.assertEqual(r.situacao, "verde")

    def test_situacao_vermelha_quando_a_mais_recente_e_vermelha(self):
        pasta = self.ficha()
        gravar(pasta / "06-auditorias" / "2026-11-20-construcao.md",
               auditoria(data="2026-11-20", veredito="vermelho", pendencia="p", prazo="2026-12-01", dono="mantenedor"))
        self.assertEqual(self.validar(pasta).situacao, "vermelho")

    # --- seção 8 ---

    def test_processos_sem_item(self):
        pasta = self.ficha()
        (pasta / "08-processos" / "runbook-subir.md").unlink()
        self.assertProblema(pasta, 8, "processo")

    def test_processo_tipo_fora_da_lista(self):
        pasta = self.ficha()
        trocar(pasta / "08-processos" / "runbook-subir.md", tipo="manual")
        self.assertProblema(pasta, 8, "tipo")

    def test_processo_sem_dono(self):
        pasta = self.ficha()
        trocar(pasta / "08-processos" / "runbook-subir.md", remover=("dono",))
        self.assertProblema(pasta, 8, "dono")

    # --- entradas difíceis ---

    def test_frontmatter_malformado_vira_problema(self):
        for bruto in ("---\nsecao: [1\n---\n# x\n", "---\n- a\n- b\n---\n# x\n", "# sem bloco\n"):
            pasta = self.ficha()
            (pasta / "01-visao.md").write_text(bruto, encoding="utf-8")
            self.assertProblema(pasta, 1, "01-visao.md")
            shutil.rmtree(pasta)

    def test_ficha_md_malformada_vira_problema(self):
        pasta = self.ficha()
        (pasta / "ficha.md").write_text("---\nslug: [x\n---\n", encoding="utf-8")
        r = self.validar(pasta)
        self.assertFalse(r.valida)

    def test_data_aceita_date_e_texto_iso(self):
        pasta = self.ficha()
        trocar(pasta / "ficha.md", data=date(2026, 11, 23))
        trocar(self.aud(pasta), data=date(2026, 11, 10))
        r = self.validar(pasta)
        self.assertTrue(r.valida, [s.problemas for s in r.secoes])

    def test_data_em_formato_invalido(self):
        pasta = self.ficha()
        trocar(self.aud(pasta), veredito="ambar", pendencia="p", dono="mantenedor", prazo="23/11/2026")
        self.assertProblema(pasta, 6, "prazo")
        trocar(pasta / "08-processos" / "runbook-subir.md", revisado_em="amanhã")
        self.assertProblema(pasta, 8, "revisado_em")

    def test_data_impossivel_vira_problema(self):
        pasta = self.ficha()
        alvo = self.aud(pasta)
        alvo.write_text(alvo.read_text(encoding="utf-8").replace("data: '2026-11-10'", "data: 2026-02-30"), encoding="utf-8")
        self.assertIn("data: 2026-02-30", alvo.read_text(encoding="utf-8"))
        self.assertProblema(pasta, 6, "2026-11-10-construcao.md")

    def test_datas_de_tipos_mistos_na_mesma_etapa(self):
        from datetime import datetime
        pasta = self.ficha()
        gravar(pasta / "06-auditorias" / "2026-11-12-construcao.md",
               auditoria(data=datetime(2026, 11, 12, 10, 0), veredito="vermelho", pendencia="p", prazo="2026-12-01", dono="mantenedor"))
        r = self.validar(pasta)
        self.assertTrue(r.valida, [s.problemas for s in r.secoes])
        self.assertEqual(r.situacao, "vermelho")

    def test_porte_que_nao_e_texto_vira_problema(self):
        for valor in (["medio"], {"a": 1}):
            pasta = self.ficha()
            trocar(pasta / "ficha.md", porte=valor)
            self.assertProblema(pasta, 0, "porte")
            shutil.rmtree(pasta)

    def test_arquivo_com_bom_e_crlf(self):
        pasta = self.ficha()
        alvo = pasta / "01-visao.md"
        texto = alvo.read_text(encoding="utf-8").replace("\n", "\r\n")
        alvo.write_bytes(b"\xef\xbb\xbf" + texto.encode("utf-8"))
        r = self.validar(pasta)
        self.assertTrue(r.valida, [s.problemas for s in r.secoes])

    def test_validar_todas_ignora_pastas_com_sublinhado(self):
        escrever_ficha(self.raiz, slug="b-demo")
        escrever_ficha(self.raiz, slug="a-demo", porte="pequeno")
        (self.raiz / "fichas" / "_modelos").mkdir()
        resultados = ficha.validar_todas(self.raiz / "fichas", self.raiz)
        self.assertEqual([r.slug for r in resultados], ["a-demo", "b-demo"])


class TestCriar(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.raiz = Path(tmp.name)
        self.fichas = self.raiz / "fichas"
        shutil.copytree(ROOT / "fichas" / "_modelos", self.fichas / "_modelos")

    def criar(self, slug="novo", nome="Projeto Novo", porte="pequeno"):
        return ficha.criar(self.fichas, slug, nome, porte, date(2026, 11, 23))

    def test_criar_pequeno_gera_so_as_secoes_do_porte(self):
        pasta = self.criar()
        for nome in ("ficha.md", "01-visao.md", "03-arquitetura.md", "04-decisoes/_secao.md"):
            self.assertTrue((pasta / nome).is_file(), nome)
        self.assertFalse((pasta / "05-prontidao.md").exists())
        self.assertFalse((pasta / "_itens").exists())

    def test_criar_grande_gera_as_onze(self):
        pasta = self.criar(porte="grande")
        for numero, nome in ficha.ARQUIVOS.items():
            self.assertTrue((pasta / nome).exists(), nome)

    def test_ficha_recem_criada_tem_campos_e_pede_preenchimento(self):
        pasta = self.criar(porte="grande", nome='Projeto: o "novo"')
        dados, _ = ler(pasta / "ficha.md")
        self.assertEqual((dados["slug"], dados["nome"], dados["porte"]), ("novo", 'Projeto: o "novo"', "grande"))
        self.assertEqual(str(dados["data"]), "2026-11-23")
        r = ficha.validar(pasta, self.raiz)
        self.assertFalse(r.valida)
        todos = [p for s in r.secoes for p in s.problemas]
        self.assertTrue(any("preench" in p for p in todos))
        self.assertFalse(any("obrigatória" in p or "malformado" in p or "'origem'" in p or "'secao'" in p for p in todos), todos)

    def test_modelos_declaram_as_dez_categorias(self):
        pasta = self.criar(porte="medio")
        dados, _ = ler(pasta / "05-prontidao.md")
        self.assertEqual(tuple(dados["categorias"]), ficha.CATEGORIAS_PRONTIDAO)

    def test_criar_recusa_pasta_existente(self):
        self.criar()
        with self.assertRaises(ficha.FichaRecusada):
            self.criar()

    def test_criar_recusa_slug_invalido(self):
        for slug in ("../x", "a/b", "a\b", "Abc", "", "_modelos", ".git", "a b"):
            with self.assertRaises(ficha.FichaRecusada, msg=slug):
                self.criar(slug=slug)
        self.assertEqual(sorted(p.name for p in self.fichas.iterdir()), ["_modelos"])
        self.assertEqual(sorted(p.name for p in self.raiz.iterdir()), ["fichas"])

    def test_criar_recusa_porte_invalido(self):
        with self.assertRaises(ficha.FichaRecusada):
            self.criar(porte="enorme")

    def test_criar_recusa_sem_modelos(self):
        shutil.rmtree(self.fichas / "_modelos")
        with self.assertRaises(ficha.FichaRecusada):
            self.criar()
        self.assertFalse((self.fichas / "novo").exists())


class TestComandos(unittest.TestCase):
    def setUp(self):
        from click.testing import CliRunner
        from unittest import mock
        import cli as modulo
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.raiz = Path(tmp.name)
        shutil.copytree(ROOT / "fichas" / "_modelos", self.raiz / "fichas" / "_modelos")
        for campo, valor in (("fichas_dir", self.raiz / "fichas"), ("base_dir", self.raiz)):
            troca = mock.patch.object(modulo.settings, campo, valor)
            troca.start()
            self.addCleanup(troca.stop)
        self.rodar = lambda *args: CliRunner().invoke(modulo.cli, ["ficha", *args])

    def test_cli_validar_sai_0_sem_problema(self):
        escrever_ficha(self.raiz, slug="demo")
        r = self.rodar("validar")
        self.assertEqual(r.exit_code, 0, r.output)
        self.assertIn("demo", r.output)
        self.assertIn("verde", r.output)

    def test_cli_validar_sai_1_com_problema(self):
        pasta = escrever_ficha(self.raiz, slug="demo")
        (pasta / "05-prontidao.md").unlink()
        r = self.rodar("validar", "demo")
        self.assertEqual(r.exit_code, 1, r.output)
        self.assertIn("05-prontidao.md", r.output)

    def test_cli_validar_slug_inexistente_sai_1(self):
        r = self.rodar("validar", "nao-existe")
        self.assertEqual(r.exit_code, 1, r.output)

    def test_cli_validar_sem_fichas_sai_0(self):
        r = self.rodar("validar")
        self.assertEqual(r.exit_code, 0, r.output)

    def test_cli_nova_cria_e_avisa(self):
        r = self.rodar("nova", "meu-projeto", "--nome", "Meu Projeto", "--porte", "pequeno")
        self.assertEqual(r.exit_code, 0, r.output)
        self.assertTrue((self.raiz / "fichas" / "meu-projeto" / "ficha.md").is_file())

    def test_cli_nova_recusada_sai_1(self):
        r = self.rodar("nova", "../fora", "--nome", "X", "--porte", "pequeno")
        self.assertEqual(r.exit_code, 1, r.output)
        self.assertFalse((self.raiz / "fora").exists())


class TestFichasDoRepositorio(unittest.TestCase):
    def test_fichas_do_repositorio_sao_validas(self):
        resultados = ficha.validar_todas(ROOT / "fichas", ROOT)
        invalidas = [(r.slug, r.problemas, [s.problemas for s in r.secoes]) for r in resultados if not r.valida]
        self.assertEqual(invalidas, [])
        self.assertIn("rag-dojo", [r.slug for r in resultados])
        self.assertIn("second-brain-open", [r.slug for r in resultados])


if __name__ == "__main__":
    unittest.main()
