from flask import Flask, render_template, request, redirect, flash, session, url_for, send_file
import sqlite3
import os
from io import BytesIO
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from werkzeug.security import check_password_hash, generate_password_hash
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

PASTA_APP = Path(__file__).resolve().parent
BANCO_DADOS = PASTA_APP / "banco_demonstracao.db"

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY")

UPLOAD_FOLDER = "static/uploads/atividades"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def conectar_banco():
    conexao = sqlite3.connect(BANCO_DADOS)
    conexao.row_factory = sqlite3.Row
    return conexao


def garantir_coluna_ativo_turmas():
    conexao = conectar_banco()
    try:
        colunas = conexao.execute("PRAGMA table_info(turmas)").fetchall()
        nomes_colunas = [coluna["name"] for coluna in colunas]
        if "ativo" not in nomes_colunas:
            conexao.execute("""
                ALTER TABLE turmas
                ADD COLUMN ativo INTEGER NOT NULL DEFAULT 1
            """)
            conexao.commit()
            print("Coluna 'ativo' adicionada à tabela turmas.")
        else:
            print("Coluna 'ativo' da tabela turmas já existe.")
    finally:
        conexao.close()


garantir_coluna_ativo_turmas()


# ==========================================================
# AUTENTICAÇÃO
# ==========================================================
@app.before_request
def verificar_login():
    if request.endpoint in ("login", "static"):
        return
    if "usuario_id" not in session:
        return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario = request.form.get("usuario", "").strip()
        senha = request.form.get("senha", "")
        conexao = conectar_banco()
        usuario_banco = conexao.execute(
            """
            SELECT *
            FROM usuarios
            WHERE usuario = ?
              AND ativo = 1
            """,
            (usuario,)
        ).fetchone()
        conexao.close()

        if usuario_banco and check_password_hash(usuario_banco["senha"], senha):
            session.clear()
            session["usuario_id"] = usuario_banco["id"]
            session["usuario_nome"] = usuario_banco["nome"]
            session["usuario"] = usuario_banco["usuario"]
            session["tipo"] = usuario_banco["tipo"]
            flash("Login realizado com sucesso!", "sucesso")
            return redirect("/")

        flash("Usuário ou senha inválidos.", "erro")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Você saiu do sistema.", "sucesso")
    return redirect(url_for("login"))


# ==========================================================
# ALTERAR SENHA DO USUÁRIO LOGADO
# ==========================================================
@app.route("/alterar_senha", methods=["GET", "POST"])
def alterar_senha():
    if request.method == "POST":
        senha_atual = request.form.get("senha_atual", "")
        nova_senha = request.form.get("nova_senha", "")
        confirmar_senha = request.form.get("confirmar_senha", "")

        if len(nova_senha) < 8:
            flash("A nova senha deve ter pelo menos 8 caracteres.", "erro")
            return render_template("alterar_senha.html")

        if nova_senha != confirmar_senha:
            flash("A confirmação não corresponde à nova senha.", "erro")
            return render_template("alterar_senha.html")

        conexao = conectar_banco()

        try:
            usuario = conexao.execute(
                """
                SELECT id, senha
                FROM usuarios
                WHERE id = ? AND ativo = 1
                """,
                (session["usuario_id"],)
            ).fetchone()

            if not usuario or not check_password_hash(
                usuario["senha"], senha_atual
            ):
                flash("A senha atual está incorreta.", "erro")
                return render_template("alterar_senha.html")

            senha_hash = generate_password_hash(nova_senha)

            conexao.execute(
                "UPDATE usuarios SET senha = ? WHERE id = ?",
                (senha_hash, usuario["id"])
            )
            conexao.commit()

            flash("Senha alterada com sucesso!", "sucesso")
            return redirect(url_for("alterar_senha"))

        finally:
            conexao.close()

    return render_template("alterar_senha.html")



@app.route("/")
def inicio():
    return render_template("index.html")


# ==========================================================
# ALUNOS
# ==========================================================
@app.route("/alunos")
def alunos():
    conexao = conectar_banco()
    try:
        lista_alunos = conexao.execute(
            """
            SELECT *
            FROM alunos
            WHERE ativo = 1
            ORDER BY nome
            """
        ).fetchall()

        turmas = conexao.execute(
            """
            SELECT turmas.*, projetos.nome AS projeto_nome
            FROM turmas
            LEFT JOIN projetos ON turmas.projeto_id = projetos.id
            WHERE turmas.ativo = 1
            ORDER BY projetos.nome, modalidade, nome
            """
        ).fetchall()

        return render_template(
            "alunos.html",
            alunos=lista_alunos,
            turmas=turmas,
            aluno_edicao=None,
            turma_edicao_id=""
        )
    finally:
        conexao.close()


# ==========================================================
# TURMAS: LISTAR, CADASTRAR, EDITAR E INATIVAR
# ==========================================================
@app.route("/turmas")
def turmas():
    conexao = conectar_banco()
    try:
        lista_turmas = conexao.execute("""
            SELECT
                t.*,
                p.nome AS projeto_nome,
                n.nome AS nucleo_nome
            FROM turmas t
            LEFT JOIN projetos p ON t.projeto_id = p.id
            LEFT JOIN nucleos n ON t.nucleo_id = n.id
            WHERE t.ativo = 1
            ORDER BY p.nome, t.modalidade, t.nome
        """).fetchall()

        projetos = conexao.execute("""
            SELECT id, nome
            FROM projetos
            WHERE ativo = 1
            ORDER BY nome
        """).fetchall()

        return render_template(
            "turmas.html",
            turmas=lista_turmas,
            projetos=projetos,
            turma_edicao=None
        )
    finally:
        conexao.close()


@app.route("/turmas/cadastrar", methods=["POST"])
def cadastrar_turma():
    projeto_id = request.form.get("projeto_id", "").strip()
    nucleo_id = request.form.get("nucleo_id", "").strip()
    modalidade = request.form.get("modalidade", "").strip()
    nome = request.form.get("nome", "").strip()
    professor = request.form.get("professor", "").strip()

    if not all([projeto_id, nucleo_id, modalidade, nome, professor]):
        flash("Preencha todos os campos da turma.", "erro")
        return redirect(url_for("turmas"))

    conexao = conectar_banco()
    try:
        projeto = conexao.execute("""
            SELECT id FROM projetos
            WHERE id = ? AND ativo = 1
        """, (projeto_id,)).fetchone()

        nucleo = conexao.execute("""
            SELECT id FROM nucleos
            WHERE id = ? AND projeto_id = ? AND ativo = 1
        """, (nucleo_id, projeto_id)).fetchone()

        if projeto is None or nucleo is None:
            flash("Projeto ou núcleo inválido. Confira a seleção.", "erro")
            return redirect(url_for("turmas"))

        conexao.execute("""
            INSERT INTO turmas (
                projeto_id, nucleo_id, modalidade, nome, professor, ativo
            )
            VALUES (?, ?, ?, ?, ?, 1)
        """, (projeto_id, nucleo_id, modalidade, nome, professor))

        conexao.commit()
        flash("Turma cadastrada com sucesso!", "sucesso")
    except sqlite3.Error:
        conexao.rollback()
        flash("Não foi possível cadastrar a turma.", "erro")
    finally:
        conexao.close()

    return redirect(url_for("turmas"))


@app.route("/turmas/editar/<int:turma_id>", methods=["GET", "POST"])
def editar_turma(turma_id):
    conexao = conectar_banco()
    try:
        turma = conexao.execute("""
            SELECT *
            FROM turmas
            WHERE id = ? AND ativo = 1
        """, (turma_id,)).fetchone()

        if turma is None:
            flash("Turma não encontrada ou já inativa.", "erro")
            return redirect(url_for("turmas"))

        projetos = conexao.execute("""
            SELECT id, nome
            FROM projetos
            WHERE ativo = 1
            ORDER BY nome
        """).fetchall()

        if request.method == "POST":
            projeto_id = request.form.get("projeto_id", "").strip()
            nucleo_id = request.form.get("nucleo_id", "").strip()
            modalidade = request.form.get("modalidade", "").strip()
            nome = request.form.get("nome", "").strip()
            professor = request.form.get("professor", "").strip()

            if not all([projeto_id, nucleo_id, modalidade, nome, professor]):
                flash("Preencha todos os campos da turma.", "erro")
                return redirect(url_for("editar_turma", turma_id=turma_id))

            projeto = conexao.execute("""
                SELECT id FROM projetos
                WHERE id = ? AND ativo = 1
            """, (projeto_id,)).fetchone()

            nucleo = conexao.execute("""
                SELECT id FROM nucleos
                WHERE id = ? AND projeto_id = ? AND ativo = 1
            """, (nucleo_id, projeto_id)).fetchone()

            if projeto is None or nucleo is None:
                flash("Projeto ou núcleo inválido. Confira a seleção.", "erro")
                return redirect(url_for("editar_turma", turma_id=turma_id))

            conexao.execute("""
                UPDATE turmas
                SET projeto_id = ?,
                    nucleo_id = ?,
                    modalidade = ?,
                    nome = ?,
                    professor = ?
                WHERE id = ? AND ativo = 1
            """, (
                projeto_id, nucleo_id, modalidade,
                nome, professor, turma_id
            ))

            # Atualiza os dados atuais dos alunos vinculados pelos campos antigos.
            conexao.execute("""
                UPDATE alunos
                SET modalidade = ?,
                    turma = ?,
                    professor = ?
                WHERE ativo = 1
                  AND turma = ?
                  AND modalidade = ?
                  AND professor = ?
            """, (
                modalidade, nome, professor,
                turma["nome"], turma["modalidade"], turma["professor"]
            ))

            conexao.commit()
            flash("Turma atualizada com sucesso!", "sucesso")
            return redirect(url_for("turmas"))

        lista_turmas = conexao.execute("""
            SELECT
                t.*,
                p.nome AS projeto_nome,
                n.nome AS nucleo_nome
            FROM turmas t
            LEFT JOIN projetos p ON t.projeto_id = p.id
            LEFT JOIN nucleos n ON t.nucleo_id = n.id
            WHERE t.ativo = 1
            ORDER BY p.nome, t.modalidade, t.nome
        """).fetchall()

        return render_template(
            "turmas.html",
            turmas=lista_turmas,
            projetos=projetos,
            turma_edicao=turma
        )
    except sqlite3.Error:
        conexao.rollback()
        flash("Ocorreu um erro ao atualizar a turma.", "erro")
        return redirect(url_for("turmas"))
    finally:
        conexao.close()


@app.route("/turmas/inativar/<int:turma_id>", methods=["POST"])
def inativar_turma(turma_id):
    conexao = conectar_banco()
    try:
        turma = conexao.execute("""
            SELECT id, nome, ativo
            FROM turmas
            WHERE id = ?
        """, (turma_id,)).fetchone()

        if turma is None or turma["ativo"] != 1:
            flash("Turma não encontrada ou já inativa.", "erro")
            return redirect(url_for("turmas"))

        conexao.execute(
            "UPDATE turmas SET ativo = 0 WHERE id = ?",
            (turma_id,)
        )
        conexao.commit()
        flash(
            f'Turma "{turma["nome"]}" inativada. '
            "Os registros históricos foram preservados.",
            "sucesso"
        )
    except sqlite3.Error:
        conexao.rollback()
        flash("Não foi possível inativar a turma.", "erro")
    finally:
        conexao.close()

    return redirect(url_for("turmas"))


# ==========================================================
# CADASTRAR E EDITAR ALUNOS
# ==========================================================
@app.route("/alunos/cadastrar", methods=["POST"])
def cadastrar_aluno():
    nome = request.form.get("nome", "").strip()
    cpf = request.form.get("cpf", "").strip()
    endereco = request.form.get("endereco", "").strip()
    data_nascimento = request.form.get("data_nascimento", "").strip()
    turma_id = request.form.get("turma_id", "").strip()

    if not nome or not turma_id:
        flash("Informe o nome do aluno e selecione uma turma.", "erro")
        return redirect(url_for("alunos"))

    conexao = conectar_banco()
    try:
        turma = conexao.execute("""
            SELECT *
            FROM turmas
            WHERE id = ? AND ativo = 1
        """, (turma_id,)).fetchone()

        if turma is None:
            flash("Turma não encontrada ou inativa.", "erro")
            return redirect(url_for("alunos"))

        conexao.execute("""
            INSERT INTO alunos (
                nome, cpf, endereco, data_nascimento,
                modalidade, turma, professor
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            nome, cpf, endereco, data_nascimento,
            turma["modalidade"], turma["nome"], turma["professor"]
        ))
        conexao.commit()
        flash("Aluno cadastrado com sucesso!", "sucesso")
    except sqlite3.Error:
        conexao.rollback()
        flash("Não foi possível cadastrar o aluno.", "erro")
    finally:
        conexao.close()

    return redirect(url_for("alunos"))


@app.route("/alunos/editar/<int:aluno_id>", methods=["GET", "POST"])
def editar_aluno(aluno_id):
    conexao = conectar_banco()
    try:
        aluno = conexao.execute("""
            SELECT *
            FROM alunos
            WHERE id = ? AND ativo = 1
        """, (aluno_id,)).fetchone()

        if aluno is None:
            flash("Aluno não encontrado ou inativo.", "erro")
            return redirect(url_for("alunos"))

        turmas = conexao.execute("""
            SELECT turmas.*, projetos.nome AS projeto_nome
            FROM turmas
            LEFT JOIN projetos ON turmas.projeto_id = projetos.id
            WHERE turmas.ativo = 1
            ORDER BY projetos.nome, modalidade, nome
        """).fetchall()

        turma_atual = conexao.execute("""
            SELECT id
            FROM turmas
            WHERE nome = ? AND modalidade = ? AND professor = ?
            LIMIT 1
        """, (aluno["turma"], aluno["modalidade"], aluno["professor"])).fetchone()

        turma_edicao_id = turma_atual["id"] if turma_atual else ""

        if request.method == "POST":
            nome = request.form.get("nome", "").strip()
            cpf = request.form.get("cpf", "").strip()
            endereco = request.form.get("endereco", "").strip()
            data_nascimento = request.form.get("data_nascimento", "").strip()
            turma_id = request.form.get("turma_id", "").strip()

            if not nome or not turma_id:
                flash("Informe o nome do aluno e selecione uma turma.", "erro")
                return redirect(url_for("editar_aluno", aluno_id=aluno_id))

            turma = conexao.execute("""
                SELECT id, nome, modalidade, professor
                FROM turmas
                WHERE id = ? AND ativo = 1
            """, (turma_id,)).fetchone()

            if turma is None:
                flash("Turma não encontrada ou inativa.", "erro")
                return redirect(url_for("editar_aluno", aluno_id=aluno_id))

            conexao.execute("""
                UPDATE alunos
                SET nome = ?, cpf = ?, endereco = ?, data_nascimento = ?,
                    modalidade = ?, turma = ?, professor = ?
                WHERE id = ? AND ativo = 1
            """, (
                nome, cpf, endereco, data_nascimento,
                turma["modalidade"], turma["nome"], turma["professor"], aluno_id
            ))
            conexao.commit()
            flash("Dados do aluno atualizados com sucesso!", "sucesso")
            return redirect(url_for("alunos"))

        lista_alunos = conexao.execute("""
            SELECT * FROM alunos
            WHERE ativo = 1
            ORDER BY nome
        """).fetchall()

        return render_template(
            "alunos.html",
            alunos=lista_alunos,
            turmas=turmas,
            aluno_edicao=aluno,
            turma_edicao_id=turma_edicao_id
        )
    except sqlite3.Error:
        conexao.rollback()
        flash("Erro ao processar os dados do aluno.", "erro")
        return redirect(url_for("alunos"))
    finally:
        conexao.close()


@app.route("/alunos/inativar/<int:aluno_id>", methods=["POST"])
def inativar_aluno(aluno_id):
    conexao = conectar_banco()
    try:
        aluno = conexao.execute("""
            SELECT id, nome, ativo
            FROM alunos
            WHERE id = ?
        """, (aluno_id,)).fetchone()

        if aluno is None or aluno["ativo"] != 1:
            flash("Aluno não encontrado ou já inativo.", "erro")
            return redirect(url_for("alunos"))

        conexao.execute("UPDATE alunos SET ativo = 0 WHERE id = ?", (aluno_id,))
        conexao.commit()
        flash(
            f'Aluno "{aluno["nome"]}" inativado com sucesso. '
            "O histórico foi preservado.",
            "sucesso"
        )
    except sqlite3.Error:
        conexao.rollback()
        flash("Não foi possível inativar o aluno.", "erro")
    finally:
        conexao.close()

    return redirect(url_for("alunos"))


# ==========================================================
# FREQUÊNCIA
# ==========================================================
@app.route("/frequencia")
def frequencia():
    conexao = conectar_banco()
    projeto_id = request.args.get("projeto_id", "")
    modalidade = request.args.get("modalidade", "")
    turma_id = request.args.get("turma_id", "")

    projetos = conexao.execute("""
        SELECT id, nome
        FROM projetos
        WHERE ativo = 1
        ORDER BY nome
    """).fetchall()

    consulta_modalidades = """
        SELECT DISTINCT modalidade
        FROM turmas
        WHERE ativo = 1
          AND modalidade IS NOT NULL
          AND modalidade != ''
    """
    parametros_modalidades = []
    if projeto_id:
        consulta_modalidades += " AND projeto_id = ?"
        parametros_modalidades.append(projeto_id)
    consulta_modalidades += " ORDER BY modalidade"
    modalidades = conexao.execute(
        consulta_modalidades, parametros_modalidades
    ).fetchall()

    consulta_turmas = """
        SELECT id, nome, modalidade, projeto_id
        FROM turmas
        WHERE ativo = 1
    """
    parametros_turmas = []
    if projeto_id:
        consulta_turmas += " AND projeto_id = ?"
        parametros_turmas.append(projeto_id)
    if modalidade:
        consulta_turmas += " AND modalidade = ?"
        parametros_turmas.append(modalidade)
    consulta_turmas += " ORDER BY nome"
    turmas = conexao.execute(consulta_turmas, parametros_turmas).fetchall()

    alunos_lista = []
    if turma_id:
        turma_selecionada = conexao.execute("""
            SELECT id, nome, modalidade, projeto_id
            FROM turmas
            WHERE id = ? AND ativo = 1
        """, (turma_id,)).fetchone()

        if turma_selecionada:
            projeto_confere = (
                not projeto_id
                or str(turma_selecionada["projeto_id"]) == projeto_id
            )
            modalidade_confere = (
                not modalidade
                or turma_selecionada["modalidade"] == modalidade
            )
            if projeto_confere and modalidade_confere:
                alunos_lista = conexao.execute("""
                    SELECT *
                    FROM alunos
                    WHERE ativo = 1 AND turma = ?
                    ORDER BY nome
                """, (turma_selecionada["nome"],)).fetchall()
            else:
                turma_id = ""
        else:
            turma_id = ""

    conexao.close()
    return render_template(
        "frequencia.html",
        projetos=projetos,
        modalidades=modalidades,
        turmas=turmas,
        alunos=alunos_lista,
        projeto_id=projeto_id,
        modalidade=modalidade,
        turma_id=turma_id
    )


@app.route("/frequencia/registrar", methods=["POST"])
def registrar_frequencia():
    data = request.form.get("data", "")
    turma_id = request.form.get("turma_id", "")
    projeto_id = request.form.get("projeto_id", "")
    modalidade = request.form.get("modalidade", "")
    filtros = {}
    if projeto_id:
        filtros["projeto_id"] = projeto_id
    if modalidade:
        filtros["modalidade"] = modalidade
    if turma_id:
        filtros["turma_id"] = turma_id

    if not data or not turma_id:
        flash("Selecione a data e a turma.", "erro")
        return redirect(url_for("frequencia", **filtros))

    conexao = conectar_banco()
    try:
        turma = conexao.execute("""
            SELECT id, nome, modalidade, professor
            FROM turmas
            WHERE id = ? AND ativo = 1
        """, (turma_id,)).fetchone()

        if turma is None:
            flash("Turma não encontrada ou inativa.", "erro")
            return redirect(url_for("frequencia", **filtros))

        alunos_lista = conexao.execute("""
            SELECT id, nome
            FROM alunos
            WHERE ativo = 1
              AND turma = ?
              AND modalidade = ?
              AND professor = ?
            ORDER BY nome
        """, (turma["nome"], turma["modalidade"], turma["professor"])).fetchall()

        if not alunos_lista:
            flash("Nenhum aluno ativo encontrado nessa turma.", "erro")
            return redirect(url_for("frequencia", **filtros))

        registros = []
        for aluno in alunos_lista:
            status = request.form.get(f"frequencia_{aluno['id']}")
            if status not in ("presente", "falta", "falta_justificada"):
                flash(f"Selecione a situação de {aluno['nome']}.", "erro")
                return redirect(url_for("frequencia", **filtros))

            if status == "presente":
                presente, justificativa = 1, None
            elif status == "falta_justificada":
                presente, justificativa = 0, "Falta justificada"
            else:
                presente, justificativa = 0, None

            registros.append((aluno["id"], data, presente, justificativa))

        for aluno_id, data_registro, _, _ in registros:
            existente = conexao.execute("""
                SELECT id
                FROM frequencias
                WHERE aluno_id = ? AND data = ?
                LIMIT 1
            """, (aluno_id, data_registro)).fetchone()
            if existente:
                flash(
                    "Já existe frequência registrada para um ou mais alunos "
                    "dessa turma nessa data. Nenhuma alteração foi feita.",
                    "erro"
                )
                return redirect(url_for("frequencia", **filtros))

        conexao.executemany("""
            INSERT INTO frequencias (aluno_id, data, presente, justificativa)
            VALUES (?, ?, ?, ?)
        """, registros)
        conexao.commit()
        flash(
            f"Chamada registrada! {len(registros)} alunos processados, "
            "incluindo faltas justificadas.",
            "sucesso"
        )
    except Exception:
        conexao.rollback()
        flash(
            "Ocorreu um erro ao registrar a chamada. Nenhum registro foi salvo.",
            "erro"
        )
    finally:
        conexao.close()

    return redirect(url_for("frequencia", **filtros))


# ==========================================================
# RELATÓRIO DE FREQUÊNCIA + EXPORTAÇÃO EXCEL
# ==========================================================
@app.route("/relatorio")
def relatorio():
    from datetime import datetime

    conexao = conectar_banco()
    hoje = datetime.now()
    mes = request.args.get("mes") or hoje.strftime("%m")
    ano = request.args.get("ano") or hoje.strftime("%Y")
    projeto_id = request.args.get("projeto_id", "")
    modalidade = request.args.get("modalidade", "")
    turma_id = request.args.get("turma_id", "")

    projetos = conexao.execute("""
        SELECT id, nome
        FROM projetos
        WHERE ativo = 1
        ORDER BY nome
    """).fetchall()

    consulta_modalidades = """
        SELECT DISTINCT modalidade
        FROM turmas
        WHERE modalidade IS NOT NULL AND modalidade != ''
    """
    parametros_modalidades = []
    if projeto_id:
        consulta_modalidades += " AND projeto_id = ?"
        parametros_modalidades.append(projeto_id)
    consulta_modalidades += " ORDER BY modalidade"
    modalidades = conexao.execute(
        consulta_modalidades, parametros_modalidades
    ).fetchall()

    consulta_turmas = """
        SELECT id, nome, modalidade, professor, projeto_id
        FROM turmas
        WHERE 1 = 1
    """
    parametros_turmas = []
    if projeto_id:
        consulta_turmas += " AND projeto_id = ?"
        parametros_turmas.append(projeto_id)
    if modalidade:
        consulta_turmas += " AND modalidade = ?"
        parametros_turmas.append(modalidade)
    consulta_turmas += " ORDER BY nome"
    turmas_lista = conexao.execute(
        consulta_turmas, parametros_turmas
    ).fetchall()

    consulta_alunos = """
        SELECT alunos.*
        FROM alunos
        WHERE alunos.ativo = 1
    """
    parametros_alunos = []
    if modalidade:
        consulta_alunos += " AND alunos.modalidade = ?"
        parametros_alunos.append(modalidade)
    if projeto_id or turma_id:
        consulta_alunos += """
            AND EXISTS (
                SELECT 1
                FROM turmas t
                WHERE t.nome = alunos.turma
                  AND t.modalidade = alunos.modalidade
                  AND t.professor = alunos.professor
        """
        if projeto_id:
            consulta_alunos += " AND t.projeto_id = ?"
            parametros_alunos.append(projeto_id)
        if turma_id:
            consulta_alunos += " AND t.id = ?"
            parametros_alunos.append(turma_id)
        consulta_alunos += ")"

    consulta_alunos += " ORDER BY alunos.nome"
    alunos_lista = conexao.execute(
        consulta_alunos, parametros_alunos
    ).fetchall()

    resultado = []
    total_alunos = total_presencas = total_faltas = 0
    total_faltas_justificadas = total_registros = 0

    for aluno in alunos_lista:
        consulta_frequencias = """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN f.presente = 1 THEN 1 ELSE 0 END) AS presencas,
                SUM(
                    CASE WHEN f.presente = 0
                      AND COALESCE(f.justificativa, '') != 'Falta justificada'
                    THEN 1 ELSE 0 END
                ) AS faltas,
                SUM(
                    CASE WHEN f.justificativa = 'Falta justificada'
                    THEN 1 ELSE 0 END
                ) AS faltas_justificadas
            FROM frequencias f
            WHERE f.aluno_id = ?
              AND strftime('%m', f.data) = ?
              AND strftime('%Y', f.data) = ?
        """
        parametros_frequencias = [aluno["id"], mes, ano]

        if projeto_id or turma_id:
            consulta_frequencias += """
                AND (
                    (
                        f.atividade_id IS NOT NULL
                        AND EXISTS (
                            SELECT 1 FROM atividades a
                            WHERE a.id = f.atividade_id
            """
            if projeto_id:
                consulta_frequencias += " AND a.projeto_id = ?"
                parametros_frequencias.append(projeto_id)
            if turma_id:
                consulta_frequencias += " AND a.turma_id = ?"
                parametros_frequencias.append(turma_id)
            consulta_frequencias += """
                        )
                    )
                    OR (
                        f.atividade_id IS NULL
                        AND EXISTS (
                            SELECT 1 FROM turmas t
                            WHERE t.nome = ?
                              AND t.modalidade = ?
                              AND t.professor = ?
            """
            parametros_frequencias.extend([
                aluno["turma"], aluno["modalidade"], aluno["professor"]
            ])
            if projeto_id:
                consulta_frequencias += " AND t.projeto_id = ?"
                parametros_frequencias.append(projeto_id)
            if turma_id:
                consulta_frequencias += " AND t.id = ?"
                parametros_frequencias.append(turma_id)
            consulta_frequencias += """
                        )
                    )
                )
            """

        frequencia_aluno = conexao.execute(
            consulta_frequencias, parametros_frequencias
        ).fetchone()

        total = frequencia_aluno["total"] or 0
        presencas = frequencia_aluno["presencas"] or 0
        faltas = frequencia_aluno["faltas"] or 0
        faltas_justificadas = frequencia_aluno["faltas_justificadas"] or 0
        if total == 0:
            continue

        percentual = (presencas / total) * 100 if total else 0
        total_alunos += 1
        total_presencas += presencas
        total_faltas += faltas
        total_faltas_justificadas += faltas_justificadas
        total_registros += total

        resultado.append({
            "nome": aluno["nome"],
            "modalidade": aluno["modalidade"],
            "turma": aluno["turma"],
            "professor": aluno["professor"],
            "presencas": presencas,
            "faltas": faltas,
            "faltas_justificadas": faltas_justificadas,
            "total": total,
            "percentual": round(percentual, 1),
        })

    percentual_geral = (
        (total_presencas / total_registros) * 100 if total_registros else 0
    )

    consulta_atividades = """
        SELECT COUNT(*)
        FROM atividades
        WHERE strftime('%m', data) = ?
          AND strftime('%Y', data) = ?
    """
    parametros_atividades = [mes, ano]
    if projeto_id:
        consulta_atividades += " AND projeto_id = ?"
        parametros_atividades.append(projeto_id)
    if modalidade:
        consulta_atividades += " AND modalidade = ?"
        parametros_atividades.append(modalidade)
    if turma_id:
        consulta_atividades += " AND turma_id = ?"
        parametros_atividades.append(turma_id)

    total_atividades = conexao.execute(
        consulta_atividades, parametros_atividades
    ).fetchone()[0]

    if request.args.get("exportar") == "excel":
        arquivo = Workbook()
        resumo = arquivo.active
        resumo.title = "Resumo"
        resumo.append(["RELATÓRIO DE FREQUÊNCIA - INSEL"])
        resumo.append(["Período", f"{mes}/{ano}"])
        nome_projeto = next(
            (p["nome"] for p in projetos if str(p["id"]) == str(projeto_id)),
            "Todos os projetos"
        ) if projeto_id else "Todos os projetos"
        resumo.append(["Projeto", nome_projeto])
        resumo.append(["Modalidade", modalidade or "Todas as modalidades"])
        nome_turma = next(
            (t["nome"] for t in turmas_lista if str(t["id"]) == str(turma_id)),
            "Todas as turmas"
        ) if turma_id else "Todas as turmas"
        resumo.append(["Turma", nome_turma])
        resumo.append([])
        resumo.append(["Indicador", "Quantidade"])
        resumo.append(["Alunos com frequência", total_alunos])
        resumo.append(["Atividades registradas", total_atividades])
        resumo.append(["Presenças", total_presencas])
        resumo.append(["Faltas não justificadas", total_faltas])
        resumo.append(["Faltas justificadas", total_faltas_justificadas])
        resumo.append(["Presença geral (%)", round(percentual_geral, 1)])

        planilha = arquivo.create_sheet("Frequência")
        planilha.append([
            "Aluno", "Modalidade", "Turma", "Professor", "Presenças",
            "Faltas", "Faltas justificadas", "Total de registros", "Presença (%)"
        ])
        for item in resultado:
            planilha.append([
                item["nome"], item["modalidade"], item["turma"],
                item["professor"], item["presencas"], item["faltas"],
                item["faltas_justificadas"], item["total"], item["percentual"]
            ])

        for aba in arquivo.worksheets:
            aba.freeze_panes = "A2"
            for celula in aba[1]:
                celula.font = Font(bold=True, color="FFFFFF")
                celula.fill = PatternFill("solid", fgColor="222222")
                celula.alignment = Alignment(horizontal="center")
            for coluna in aba.columns:
                largura = max(
                    (len(str(c.value)) for c in coluna if c.value is not None),
                    default=10
                )
                aba.column_dimensions[coluna[0].column_letter].width = min(
                    largura + 3, 40
                )

        memoria = BytesIO()
        arquivo.save(memoria)
        memoria.seek(0)
        conexao.close()
        return send_file(
            memoria,
            as_attachment=True,
            download_name=f"relatorio_frequencia_{ano}_{mes}.xlsx",
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    conexao.close()
    return render_template(
        "relatorio.html",
        alunos=resultado,
        mes=mes,
        ano=ano,
        projetos=projetos,
        projeto_id=projeto_id,
        modalidades=modalidades,
        modalidade=modalidade,
        turmas=turmas_lista,
        turma_id=turma_id,
        total_alunos=total_alunos,
        total_atividades=total_atividades,
        total_presencas=total_presencas,
        total_faltas=total_faltas,
        total_faltas_justificadas=total_faltas_justificadas,
        percentual_geral=round(percentual_geral, 1),
    )


# ==========================================================
# ATIVIDADES
# ==========================================================
@app.route("/atividades")
def atividades():
    conexao = conectar_banco()
    try:
        turmas_lista = conexao.execute("""
            SELECT turmas.*, projetos.nome AS projeto_nome
            FROM turmas
            LEFT JOIN projetos ON turmas.projeto_id = projetos.id
            WHERE turmas.ativo = 1
            ORDER BY projetos.nome, modalidade, nome
        """).fetchall()

        # Mantém o histórico completo, inclusive de turmas inativadas.
        atividades_registradas = conexao.execute("""
            SELECT
                atividades.id,
                atividades.data,
                atividades.horario,
                atividades.modalidade,
                atividades.professor,
                atividades.local,
                atividades.foto,
                projetos.nome AS projeto_nome,
                turmas.nome AS turma_nome,
                COUNT(frequencias.id) AS total_alunos,
                SUM(CASE WHEN frequencias.presente = 1 THEN 1 ELSE 0 END) AS presencas,
                SUM(
                    CASE WHEN frequencias.presente = 0
                      AND (frequencias.justificativa IS NULL OR frequencias.justificativa = '')
                    THEN 1 ELSE 0 END
                ) AS faltas,
                SUM(
                    CASE WHEN frequencias.justificativa = 'Falta justificada'
                    THEN 1 ELSE 0 END
                ) AS faltas_justificadas
            FROM atividades
            LEFT JOIN projetos ON atividades.projeto_id = projetos.id
            LEFT JOIN turmas ON atividades.turma_id = turmas.id
            LEFT JOIN frequencias ON frequencias.atividade_id = atividades.id
            GROUP BY atividades.id
            ORDER BY atividades.data DESC, atividades.id DESC
        """).fetchall()

        return render_template(
            "atividades.html",
            turmas=turmas_lista,
            atividades_registradas=atividades_registradas
        )
    finally:
        conexao.close()


@app.route("/atividades/alunos/<int:turma_id>")
def alunos_da_turma(turma_id):
    conexao = conectar_banco()
    try:
        turma = conexao.execute("""
            SELECT id, nome, modalidade, professor
            FROM turmas
            WHERE id = ? AND ativo = 1
        """, (turma_id,)).fetchone()

        if turma is None:
            return []

        alunos_lista = conexao.execute("""
            SELECT id, nome
            FROM alunos
            WHERE ativo = 1
              AND turma = ?
              AND modalidade = ?
              AND professor = ?
            ORDER BY nome
        """, (turma["nome"], turma["modalidade"], turma["professor"])).fetchall()

        return [{"id": aluno["id"], "nome": aluno["nome"]} for aluno in alunos_lista]
    finally:
        conexao.close()


@app.route("/atividades/cadastrar", methods=["POST"])
def cadastrar_atividade():
    data = request.form.get("data", "").strip()
    horario = request.form.get("horario", "").strip()
    turma_id = request.form.get("turma_id", "").strip()
    local = request.form.get("local", "").strip()
    foto = request.files.get("foto")
    nome_foto = None

    conexao = conectar_banco()
    try:
        turma = conexao.execute("""
            SELECT turmas.*, projetos.nome AS projeto_nome
            FROM turmas
            LEFT JOIN projetos ON turmas.projeto_id = projetos.id
            WHERE turmas.id = ? AND turmas.ativo = 1
        """, (turma_id,)).fetchone()

        if turma is None:
            flash("Turma não encontrada ou inativa.", "erro")
            return redirect(url_for("atividades"))

        if not data or not horario or not local:
            flash("Preencha a data, o horário e o local da atividade.", "erro")
            return redirect(url_for("atividades"))

        if foto and foto.filename:
            nome_foto = os.path.basename(foto.filename)
            caminho_foto = os.path.join(UPLOAD_FOLDER, nome_foto)
            foto.save(caminho_foto)

        cursor = conexao.execute("""
            INSERT INTO atividades (
                data, horario, projeto_id, turma_id,
                modalidade, professor, local, foto
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data, horario, turma["projeto_id"], turma_id,
            turma["modalidade"], turma["professor"], local, nome_foto
        ))
        atividade_id = cursor.lastrowid

        alunos_lista = conexao.execute("""
            SELECT id
            FROM alunos
            WHERE ativo = 1
              AND turma = ?
              AND modalidade = ?
              AND professor = ?
        """, (turma["nome"], turma["modalidade"], turma["professor"])).fetchall()

        for aluno in alunos_lista:
            status = request.form.get(f"frequencia_{aluno['id']}")
            if status == "presente":
                presente, justificativa = 1, None
            elif status == "falta_justificada":
                presente, justificativa = 0, "Falta justificada"
            else:
                presente, justificativa = 0, None

            conexao.execute("""
                INSERT INTO frequencias (
                    aluno_id, data, presente, justificativa, atividade_id
                )
                VALUES (?, ?, ?, ?, ?)
            """, (aluno["id"], data, presente, justificativa, atividade_id))

        conexao.commit()
        flash("Atividade e frequências registradas com sucesso!", "sucesso")
    except sqlite3.Error:
        conexao.rollback()
        flash("Não foi possível cadastrar a atividade. Confira os dados e tente novamente.", "erro")
    finally:
        conexao.close()

    return redirect(url_for("atividades"))


# ==========================================================
# RELATÓRIO DE ATIVIDADES
# ==========================================================
@app.route("/relatorio-atividades")
def relatorio_atividades():
    from datetime import datetime

    conexao = conectar_banco()
    mes = request.args.get("mes")
    ano = request.args.get("ano")
    projeto_id = request.args.get("projeto_id")
    modalidade = request.args.get("modalidade")
    hoje = datetime.now()
    if not mes:
        mes = hoje.strftime("%m")
    if not ano:
        ano = hoje.strftime("%Y")

    projetos = conexao.execute("""
        SELECT *
        FROM projetos
        WHERE ativo = 1
        ORDER BY nome
    """).fetchall()

    modalidades = conexao.execute("""
        SELECT DISTINCT modalidade
        FROM turmas
        WHERE modalidade IS NOT NULL
          AND modalidade != ''
        ORDER BY modalidade
    """).fetchall()

    consulta = """
        SELECT
            atividades.id,
            atividades.data,
            atividades.horario,
            atividades.modalidade,
            atividades.professor,
            atividades.local,
            atividades.foto,
            projetos.nome AS projeto_nome,
            turmas.nome AS turma_nome,
            COUNT(frequencias.id) AS total_alunos,
            SUM(CASE WHEN frequencias.presente = 1 THEN 1 ELSE 0 END) AS presencas,
            SUM(
                CASE WHEN frequencias.presente = 0
                  AND (frequencias.justificativa IS NULL OR frequencias.justificativa = '')
                THEN 1 ELSE 0 END
            ) AS faltas,
            SUM(
                CASE WHEN frequencias.justificativa = 'Falta justificada'
                THEN 1 ELSE 0 END
            ) AS faltas_justificadas
        FROM atividades
        LEFT JOIN projetos ON atividades.projeto_id = projetos.id
        LEFT JOIN turmas ON atividades.turma_id = turmas.id
        LEFT JOIN frequencias ON frequencias.atividade_id = atividades.id
        WHERE strftime('%m', atividades.data) = ?
          AND strftime('%Y', atividades.data) = ?
    """
    parametros = [mes, ano]
    if projeto_id:
        consulta += " AND atividades.projeto_id = ?"
        parametros.append(projeto_id)
    if modalidade:
        consulta += " AND atividades.modalidade = ?"
        parametros.append(modalidade)
    consulta += """
        GROUP BY atividades.id
        ORDER BY atividades.data DESC, atividades.id DESC
    """

    atividades_registradas = conexao.execute(consulta, parametros).fetchall()
    total_atividades = len(atividades_registradas)
    total_alunos = total_presencas = total_faltas = total_faltas_justificadas = 0

    for atividade in atividades_registradas:
        total_alunos += atividade["total_alunos"] or 0
        total_presencas += atividade["presencas"] or 0
        total_faltas += atividade["faltas"] or 0
        total_faltas_justificadas += atividade["faltas_justificadas"] or 0

    total_registros = total_presencas + total_faltas + total_faltas_justificadas
    percentual_geral = (
        (total_presencas / total_registros) * 100 if total_registros else 0
    )

    conexao.close()
    return render_template(
        "relatorio_atividades.html",
        atividades_registradas=atividades_registradas,
        mes=mes,
        ano=ano,
        projetos=projetos,
        projeto_id=projeto_id,
        modalidades=modalidades,
        modalidade=modalidade,
        total_atividades=total_atividades,
        total_alunos=total_alunos,
        total_presencas=total_presencas,
        total_faltas=total_faltas,
        total_faltas_justificadas=total_faltas_justificadas,
        percentual_geral=round(percentual_geral, 1)
    )


# ==========================================================
# API DE NÚCLEOS POR PROJETO
# ==========================================================
@app.route("/api/projetos/<int:projeto_id>/nucleos", methods=["GET"])
def api_nucleos_por_projeto(projeto_id):
    conexao = conectar_banco()
    try:
        nucleos_projeto = conexao.execute("""
            SELECT id, nome
            FROM nucleos
            WHERE projeto_id = ? AND ativo = 1
            ORDER BY nome
        """, (projeto_id,)).fetchall()
        return [{"id": nucleo["id"], "nome": nucleo["nome"]} for nucleo in nucleos_projeto]
    finally:
        conexao.close()


# ==========================================================
# NÚCLEOS
# ==========================================================
@app.route("/nucleos", methods=["GET"])
def nucleos():
    conexao = conectar_banco()
    try:
        projetos = conexao.execute("""
            SELECT id, nome
            FROM projetos
            WHERE ativo = 1
            ORDER BY nome
        """).fetchall()

        lista_nucleos = conexao.execute("""
            SELECT
                n.id,
                n.nome,
                n.endereco,
                p.nome AS projeto_nome
            FROM nucleos n
            INNER JOIN projetos p ON p.id = n.projeto_id
            WHERE n.ativo = 1
            ORDER BY p.nome, n.nome
        """).fetchall()

        return render_template(
            "nucleos.html",
            projetos=projetos,
            nucleos=lista_nucleos
        )
    finally:
        conexao.close()


@app.route("/nucleos/cadastrar", methods=["POST"])
def cadastrar_nucleo():
    projeto_id = request.form.get("projeto_id", "").strip()
    nome = request.form.get("nome", "").strip()
    endereco = request.form.get("endereco", "").strip()

    if not projeto_id or not nome:
        flash("Selecione um projeto e informe o nome do núcleo.", "erro")
        return redirect(url_for("nucleos"))

    conexao = conectar_banco()
    try:
        projeto = conexao.execute("""
            SELECT id
            FROM projetos
            WHERE id = ? AND ativo = 1
        """, (projeto_id,)).fetchone()

        if projeto is None:
            flash("Projeto inválido ou inativo.", "erro")
            return redirect(url_for("nucleos"))

        conexao.execute("""
            INSERT INTO nucleos (projeto_id, nome, endereco)
            VALUES (?, ?, ?)
        """, (projeto_id, nome, endereco))
        conexao.commit()
        flash("Núcleo cadastrado com sucesso!", "sucesso")
    except sqlite3.Error:
        conexao.rollback()
        flash("Não foi possível cadastrar o núcleo.", "erro")
    finally:
        conexao.close()

    return redirect(url_for("nucleos"))



if __name__ == "__main__":
    app.run(debug=False, host="127.0.0.1", port=5000)

