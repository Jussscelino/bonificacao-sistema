import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import hashlib
import sqlite3
import os

# ============================================
# CONFIGURACAO DA PAGINA
# ============================================
st.set_page_config(
    page_title="Sistema de Bonificacao",
    page_icon="🎁",
    layout="wide"
)

# ============================================
# CONSTANTES
# ============================================
TAXA_BONIFICACAO = 0.01
DIAS_VALIDADE = 365
DB_PATH = os.environ.get("DB_PATH", "bonificacao.db")

# ============================================
# CONEXAO COM BANCO DE DADOS
# ============================================
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    """Cria as tabelas se nao existirem."""
    with get_conn() as conn:
        cur = conn.cursor()

        # Tabela de vendas (uma linha por cupom)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS vendas (
                cupom TEXT PRIMARY KEY,
                cliente TEXT NOT NULL,
                valor REAL NOT NULL,
                pontos REAL NOT NULL,
                data_venda TEXT NOT NULL,
                validade TEXT NOT NULL,
                loja TEXT,
                pagamento TEXT,
                data_upload TEXT NOT NULL
            )
        """)

        # Tabela de uploads (historico de arquivos processados)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS uploads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data_upload TEXT NOT NULL,
                arquivo TEXT NOT NULL,
                file_hash TEXT UNIQUE NOT NULL,
                registros_arquivo INTEGER NOT NULL,
                registros_novos INTEGER NOT NULL,
                registros_duplicados INTEGER NOT NULL,
                total_vendas REAL NOT NULL,
                total_pontos REAL NOT NULL
            )
        """)

        # Tabela de produtos disponiveis para resgate
        cur.execute("""
            CREATE TABLE IF NOT EXISTS produtos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                descricao TEXT,
                custo_pontos REAL NOT NULL,
                estoque INTEGER,
                ativo INTEGER DEFAULT 1
            )
        """)

        # Tabela de resgates efetuados
        cur.execute("""
            CREATE TABLE IF NOT EXISTS resgates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cliente TEXT NOT NULL,
                produto_id INTEGER NOT NULL,
                produto_nome TEXT NOT NULL,
                custo_pontos REAL NOT NULL,
                data_resgate TEXT NOT NULL,
                status TEXT DEFAULT 'CONCLUIDO',
                observacao TEXT,
                FOREIGN KEY (produto_id) REFERENCES produtos(id)
            )
        """)

        # Tabela de ajustes manuais (creditos/debitos)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS ajustes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cliente TEXT NOT NULL,
                pontos REAL NOT NULL,
                motivo TEXT,
                data_ajuste TEXT NOT NULL
            )
        """)

        conn.commit()

init_db()

# ============================================
# FUNCOES AUXILIARES
# ============================================
def calcular_pontos(valor_venda):
    return round(float(valor_venda) * TAXA_BONIFICACAO, 2)

def calcular_validade(data_venda):
    if isinstance(data_venda, str):
        data_venda = pd.to_datetime(data_venda)
    return data_venda + timedelta(days=DIAS_VALIDADE)

def normalizar_cliente(nome):
    if pd.isna(nome):
        return ""
    return " ".join(str(nome).strip().title().split())

def parse_valor(valor):
    if pd.isna(valor):
        raise ValueError("Valor vazio")
    if isinstance(valor, (int, float)):
        return float(valor)
    valor_str = str(valor).replace("R$", "").replace(" ", "").strip()
    if "," in valor_str and "." in valor_str:
        valor_str = valor_str.replace(".", "").replace(",", ".")
    elif "," in valor_str:
        valor_str = valor_str.replace(",", ".")
    return float(valor_str)

def parse_data(data):
    if pd.isna(data) or str(data).strip() == "":
        raise ValueError("Data vazia")
    if isinstance(data, datetime):
        return data
    formatos = [
        '%d/%m/%Y %H:%M:%S', '%d/%m/%Y %H:%M', '%d/%m/%Y',
        '%Y-%m-%d', '%d-%m-%Y', '%Y/%m/%d'
    ]
    data_str = str(data).strip()
    for fmt in formatos:
        try:
            return datetime.strptime(data_str, fmt)
        except ValueError:
            continue
    return pd.to_datetime(data_str)

def hash_arquivo(arquivo):
    return hashlib.md5(arquivo.getvalue()).hexdigest()

def formatar_moeda(valor):
    try:
        return "R$ " + f"{float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (ValueError, TypeError):
        return "R$ 0,00"

# ============================================
# PROCESSAMENTO DE CSV
# ============================================
def processar_csv(arquivo):
    try:
        df = pd.read_csv(arquivo, sep=';', header=None, quotechar='"', encoding='utf-8')

        if df.shape[1] < 8:
            st.error(f"O arquivo deve ter pelo menos 8 colunas. Encontradas: {df.shape[1]}.")
            return None

        df.columns = [
            'cupom', 'cliente', 'valor_total', 'desconto',
            'valor_final', 'loja', 'pagamento', 'data'
        ] + [f'extra_{i}' for i in range(df.shape[1] - 8)]

        if df.empty:
            st.error("O arquivo CSV esta vazio.")
            return None

        registros_validos = []
        erros = []

        for idx, row in df.iterrows():
            try:
                cupom = str(row['cupom']).strip() if not pd.isna(row['cupom']) else ""
                if not cupom:
                    raise ValueError("Cupom vazio")
                cliente = normalizar_cliente(row['cliente'])
                if not cliente:
                    raise ValueError("Nome do cliente vazio")
                valor = parse_valor(row['valor_final'])
                if valor < 0:
                    raise ValueError("Valor negativo")
                data = parse_data(row['data'])
                loja = str(row['loja']).strip() if not pd.isna(row['loja']) else ""
                pagamento = str(row['pagamento']).strip() if not pd.isna(row['pagamento']) else ""

                registros_validos.append({
                    'cupom': cupom,
                    'cliente': cliente,
                    'valor': valor,
                    'pontos': calcular_pontos(valor),
                    'data_venda': data.strftime('%Y-%m-%d %H:%M:%S'),
                    'validade': calcular_validade(data).strftime('%Y-%m-%d'),
                    'loja': loja,
                    'pagamento': pagamento,
                    'data_upload': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                })
            except Exception as e:
                erros.append(f"Linha {idx + 1}: {e}")

        if erros:
            with st.expander(f"{len(erros)} linha(s) com erro (ignoradas)"):
                for erro in erros:
                    st.warning(erro)

        if not registros_validos:
            st.error("Nenhuma linha valida encontrada no arquivo.")
            return None

        return pd.DataFrame(registros_validos)

    except pd.errors.EmptyDataError:
        st.error("O arquivo esta vazio ou nao e um CSV valido.")
        return None
    except Exception as e:
        st.error(f"Erro ao processar arquivo: {e}")
        return None

# ============================================
# OPERACOES NO BANCO
# ============================================
def upload_ja_processado(file_hash):
    with get_conn() as conn:
        cur = conn.execute("SELECT 1 FROM uploads WHERE file_hash = ?", (file_hash,))
        return cur.fetchone() is not None

def inserir_vendas(df_novo, arquivo_nome, file_hash):
    """Insere vendas no banco, ignorando cupons duplicados. Retorna (novos, duplicados)."""
    with get_conn() as conn:
        cur = conn.cursor()
        existentes = {r[0] for r in cur.execute("SELECT cupom FROM vendas").fetchall()}
        novos = 0
        duplicados = 0

        for _, row in df_novo.iterrows():
            if row['cupom'] in existentes:
                duplicados += 1
                continue
            cur.execute("""
                INSERT INTO vendas (cupom, cliente, valor, pontos, data_venda, validade,
                                    loja, pagamento, data_upload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                row['cupom'], row['cliente'], row['valor'], row['pontos'],
                row['data_venda'], row['validade'], row['loja'],
                row['pagamento'], row['data_upload']
            ))
            novos += 1

        # Registra upload
        cur.execute("""
            INSERT INTO uploads (data_upload, arquivo, file_hash,
                                 registros_arquivo, registros_novos, registros_duplicados,
                                 total_vendas, total_pontos)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            arquivo_nome, file_hash,
            len(df_novo), novos, duplicados,
            float(df_novo['valor'].sum()), float(df_novo['pontos'].sum())
        ))
        conn.commit()

    return novos, duplicados

def carregar_vendas():
    with get_conn() as conn:
        df = pd.read_sql_query("SELECT * FROM vendas", conn)
    return df

def carregar_uploads():
    with get_conn() as conn:
        df = pd.read_sql_query("SELECT * FROM uploads ORDER BY id DESC", conn)
    return df

def carregar_produtos(somente_ativos=True):
    with get_conn() as conn:
        sql = "SELECT * FROM produtos"
        if somente_ativos:
            sql += " WHERE ativo = 1"
        sql += " ORDER BY custo_pontos"
        df = pd.read_sql_query(sql, conn)
    return df

def carregar_resgates():
    with get_conn() as conn:
        df = pd.read_sql_query("SELECT * FROM resgates ORDER BY id DESC", conn)
    return df

def carregar_ajustes():
    with get_conn() as conn:
        df = pd.read_sql_query("SELECT * FROM ajustes ORDER BY id DESC", conn)
    return df

def inserir_produto(nome, descricao, custo_pontos, estoque):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO produtos (nome, descricao, custo_pontos, estoque)
            VALUES (?, ?, ?, ?)
        """, (nome, descricao, custo_pontos, estoque))
        conn.commit()

def atualizar_produto(produto_id, nome, descricao, custo_pontos, estoque, ativo):
    with get_conn() as conn:
        conn.execute("""
            UPDATE produtos SET nome=?, descricao=?, custo_pontos=?, estoque=?, ativo=?
            WHERE id=?
        """, (nome, descricao, custo_pontos, estoque, ativo, produto_id))
        conn.commit()

def deletar_produto(produto_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM produtos WHERE id=?", (produto_id,))
        conn.commit()

def inserir_ajuste(cliente, pontos, motivo):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO ajustes (cliente, pontos, motivo, data_ajuste)
            VALUES (?, ?, ?, ?)
        """, (cliente, pontos, motivo, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()

# ============================================
# CALCULO DE SALDO
# ============================================
def calcular_saldo_cliente(cliente):
    """
    Calcula o saldo detalhado de um cliente:
    - pontos_ativos: pontos ainda dentro da validade
    - pontos_expirados: pontos fora da validade
    - pontos_resgatados: soma dos resgates
    - pontos_ajustes: creditos (+) ou debitos (-) manuais
    - saldo_disponivel: ativos + ajustes - resgatados
    """
    hoje = pd.Timestamp.now().normalize()

    with get_conn() as conn:
        df_vendas = pd.read_sql_query(
            "SELECT * FROM vendas WHERE cliente = ?", conn, params=(cliente,)
        )
        resgates = pd.read_sql_query(
            "SELECT * FROM resgates WHERE cliente = ?", conn, params=(cliente,)
        )
        ajustes = pd.read_sql_query(
            "SELECT * FROM ajustes WHERE cliente = ?", conn, params=(cliente,)
        )

    if df_vendas.empty:
        pontos_ativos = 0.0
        pontos_expirados = 0.0
    else:
        df_vendas['validade_dt'] = pd.to_datetime(df_vendas['validade'])
        ativos = df_vendas[df_vendas['validade_dt'] >= hoje]
        expirados = df_vendas[df_vendas['validade_dt'] < hoje]
        pontos_ativos = float(ativos['pontos'].sum())
        pontos_expirados = float(expirados['pontos'].sum())

    pontos_resgatados = float(resgates['custo_pontos'].sum()) if not resgates.empty else 0.0
    pontos_ajustes = float(ajustes['pontos'].sum()) if not ajustes.empty else 0.0

    saldo_disponivel = max(0.0, pontos_ativos + pontos_ajustes - pontos_resgatados)

    return {
        'pontos_ativos': pontos_ativos,
        'pontos_expirados': pontos_expirados,
        'pontos_resgatados': pontos_resgatados,
        'pontos_ajustes': pontos_ajustes,
        'saldo_disponivel': saldo_disponivel,
        'total_gerado': pontos_ativos + pontos_expirados
    }

def saldo_disponivel_rapido(cliente):
    return calcular_saldo_cliente(cliente)['saldo_disponivel']

def listar_clientes():
    with get_conn() as conn:
        df = pd.read_sql_query(
            "SELECT DISTINCT cliente FROM vendas ORDER BY cliente", conn
        )
    return df['cliente'].tolist()

# ============================================
# REGISTRO DE RESGATE
# ============================================
def registrar_resgate(cliente, produto_id, observacao=""):
    """
    Registra um resgate, validando saldo e estoque.
    Retorna (sucesso, mensagem).
    """
    saldo = calcular_saldo_cliente(cliente)

    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM produtos WHERE id = ?", (produto_id,))
        produto = cur.fetchone()

        if not produto:
            return False, "Produto nao encontrado."

        produto_dict = {
            'id': produto[0], 'nome': produto[1], 'descricao': produto[2],
            'custo_pontos': produto[3], 'estoque': produto[4], 'ativo': produto[5]
        }

        if not produto_dict['ativo']:
            return False, "Produto inativo."

        if produto_dict['custo_pontos'] > saldo['saldo_disponivel']:
            return False, (
                f"Saldo insuficiente. Disponivel: {formatar_moeda(saldo['saldo_disponivel'])} | "
                f"Necessario: {formatar_moeda(produto_dict['custo_pontos'])}"
            )

        if produto_dict['estoque'] is not None and produto_dict['estoque'] <= 0:
            return False, "Produto sem estoque."

        # Registra resgate
        cur.execute("""
            INSERT INTO resgates (cliente, produto_id, produto_nome, custo_pontos,
                                  data_resgate, status, observacao)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            cliente, produto_dict['id'], produto_dict['nome'],
            produto_dict['custo_pontos'],
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'CONCLUIDO', observacao
        ))

        # Debita estoque
        if produto_dict['estoque'] is not None:
            cur.execute(
                "UPDATE produtos SET estoque = estoque - 1 WHERE id = ?",
                (produto_dict['id'],)
            )

        conn.commit()

    return True, (
        f"✅ Resgate concluido! {produto_dict['nome']} por "
        f"{formatar_moeda(produto_dict['custo_pontos'])}. "
        f"Novo saldo: {formatar_moeda(saldo['saldo_disponivel'] - produto_dict['custo_pontos'])}"
    )

# ============================================
# CONSILIACAO PARA EXIBICAO
# ============================================
def consolidar_clientes():
    """Retorna DataFrame com resumo por cliente (disponivel, expirado, resgatado)."""
    clientes = listar_clientes()
    if not clientes:
        return pd.DataFrame()

    registros = []
    for c in clientes:
        s = calcular_saldo_cliente(c)
        registros.append({
            'Cliente': c,
            'Total Gerado (R$)': s['total_gerado'],
            'Pontos Expirados (R$)': s['pontos_expirados'],
            'Pontos Resgatados (R$)': s['pontos_resgatados'],
            'Ajustes (R$)': s['pontos_ajustes'],
            'Saldo Disponivel (R$)': s['saldo_disponivel']
        })

    df = pd.DataFrame(registros).sort_values('Saldo Disponivel (R$)', ascending=False)
    return df

# ============================================
# INTERFACE PRINCIPAL
# ============================================
st.title("🎁 Sistema de Bonificacao de Vendas")
st.markdown("---")

with st.sidebar:
    st.header("📋 Menu")
    opcao = st.radio(
        "Selecione uma opcao:",
        [
            "📤 Upload de Vendas",
            "📊 Dashboard",
            "👥 Clientes",
            "🎁 Resgatar Pontos",
            "🛒 Gerenciar Produtos",
            "📜 Historico de Resgates",
            "⚙️ Ajustes Manuais",
            "📅 A Expirar (30 dias)",
            "⚠️ Pontos Expirados",
            "ℹ️ Informacoes"
        ]
    )

    st.markdown("---")
    st.markdown("### 💡 Como funciona")
    st.info(
        f"Cliente gasta R$ 1.000,00\n"
        f"Recebe R$ 10,00 em pontos (1%)\n"
        f"Validade: {DIAS_VALIDADE} dias\n"
        f"Dados salvos em: `{DB_PATH}`"
    )

    with get_conn() as conn:
        total_vendas = pd.read_sql_query("SELECT COUNT(*) as n FROM vendas", conn)['n'][0]
        total_resgates = pd.read_sql_query("SELECT COUNT(*) as n FROM resgates", conn)['n'][0]

    st.success(f"✅ {total_vendas} vendas | 🎁 {total_resgates} resgates")

# ============================================
# PAGINA: UPLOAD
# ============================================
if opcao == "📤 Upload de Vendas":
    st.header("📤 Upload do Arquivo de Vendas")
    st.info(
        "💡 **Acumulacao automatica:** Cada novo upload e somado ao banco de dados. "
        "Vendas duplicadas (mesmo cupom) sao ignoradas."
    )

    st.markdown("**Formato esperado (RelVendaPorData.csv):**")
    st.code(
        '"00425";"CONSUMIDOR FINAL";"3,50";"0,00";"3,50";"APOLLO32";"A VISTA";"01/08/2026  11:11:13"\n'
        '"00426";"CONSUMIDOR FINAL";"8,00";"0,00";"8,00";"APOLLO32";"A VISTA";"01/08/2026  11:43:38"',
        language="csv"
    )

    exemplo_csv = (
        '"00001";"CLIENTE EXEMPLO";"100,00";"0,00";"100,00";"LOJA";"PIX";"01/01/2025  10:00:00"\n'
        '"00002";"OUTRO CLIENTE";"250,50";"0,00";"250,50";"LOJA";"CARTÃO";"02/01/2025  14:30:00"'
    )
    st.download_button("📥 Baixar modelo", data=exemplo_csv,
                       file_name="modelo_vendas.csv", mime="text/csv")

    st.markdown("---")

    arquivo = st.file_uploader("Selecione o arquivo CSV", type=['csv'])

    if arquivo is not None:
        file_hash = hash_arquivo(arquivo)

        if upload_ja_processado(file_hash):
            st.warning("⚠️ Este arquivo ja foi processado anteriormente (mesmo hash). Upload ignorado.")
        else:
            df_novo = processar_csv(arquivo)

            if df_novo is not None:
                novos, duplicados = inserir_vendas(df_novo, arquivo.name, file_hash)

                st.success(
                    f"✅ Arquivo processado! **{novos}** novas vendas adicionadas "
                    f"({duplicados} duplicadas ignoradas)."
                )

                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Vendas no Arquivo", len(df_novo))
                with col2:
                    st.metric("Novas Vendas", novos)
                with col3:
                    st.metric("Duplicadas", duplicados)
                with col4:
                    st.metric("Total no Banco", pd.read_sql_query(
                        "SELECT COUNT(*) as n FROM vendas", get_conn()
                    )['n'][0])

                st.markdown("### 📋 Preview das Novas Vendas")
                preview = df_novo.copy()
                preview['data_venda'] = pd.to_datetime(preview['data_venda']).dt.strftime('%d/%m/%Y %H:%M')
                preview = preview.rename(columns={
                    'cupom': 'Cupom', 'cliente': 'Cliente', 'valor': 'Valor (R$)',
                    'pontos': 'Pontos (R$)', 'data_venda': 'Data',
                    'validade': 'Validade', 'loja': 'Loja', 'pagamento': 'Pagamento'
                })
                st.dataframe(
                    preview[['Cupom', 'Cliente', 'Valor (R$)', 'Pontos (R$)',
                             'Data', 'Validade', 'Loja', 'Pagamento']],
                    use_container_width=True, hide_index=True
                )

# ============================================
# PAGINA: DASHBOARD
# ============================================
elif opcao == "📊 Dashboard":
    st.header("📊 Dashboard de Vendas e Pontos")

    df = carregar_vendas()
    if df.empty:
        st.warning("Nenhum dado carregado.")
    else:
        hoje = pd.Timestamp.now().normalize()
        df['validade_dt'] = pd.to_datetime(df['validade'])
        df['expirado'] = df['validade_dt'] < hoje

        resgates = carregar_resgates()

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("💰 Total de Vendas", formatar_moeda(df['valor'].sum()))
        with col2:
            st.metric("🎁 Pontos Disponiveis", formatar_moeda(df[~df['expirado']]['pontos'].sum()))
        with col3:
            st.metric("👥 Clientes", df['cliente'].nunique())
        with col4:
            st.metric("📈 Ticket Medio", formatar_moeda(df['valor'].mean()))

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("📦 Vendas (qtd)", len(df))
        with col2:
            st.metric("🎯 Pontos Gerados", formatar_moeda(df['pontos'].sum()))
        with col3:
            st.metric("💸 Pontos Expirados", formatar_moeda(df[df['expirado']]['pontos'].sum()))
        with col4:
            resgatado = resgates['custo_pontos'].sum() if not resgates.empty else 0
            st.metric("🎁 Pontos Resgatados", formatar_moeda(resgatado))

        st.markdown("---")

        col1, col2 = st.columns(2)
        with col1:
            st.subheader("🏆 Top 10 Clientes por Valor")
            top = df.groupby('cliente')['valor'].sum().nlargest(10).reset_index()
            top.columns = ['Cliente', 'Valor']
            st.bar_chart(top.set_index('Cliente'))

        with col2:
            st.subheader("🎁 Top 10 Clientes por Pontos Disponiveis")
            top = df[~df['expirado']].groupby('cliente')['pontos'].sum().nlargest(10).reset_index()
            if top.empty:
                st.info("Nenhum ponto disponivel.")
            else:
                top.columns = ['Cliente', 'Pontos']
                st.bar_chart(top.set_index('Cliente'))

        st.markdown("---")

        if df['data_venda'].nunique() > 1:
            st.subheader("📅 Evolucao de Vendas por Data")
            df['data_str'] = pd.to_datetime(df['data_venda']).dt.strftime('%Y-%m-%d')
            vendas_data = df.groupby('data_str')['valor'].sum().reset_index()
            vendas_data.columns = ['Data', 'Valor']
            st.line_chart(vendas_data.set_index('Data'))

# ============================================
# PAGINA: CLIENTES
# ============================================
elif opcao == "👥 Clientes":
    st.header("👥 Clientes e Saldo de Pontos")

    df = consolidar_clientes()
    if df.empty:
        st.warning("Nenhum cliente cadastrado. Faca upload de vendas primeiro.")
    else:
        busca = st.text_input("🔍 Buscar cliente:", "")
        df_filtrado = df[df['Cliente'].str.contains(busca, case=False, na=False)] if busca else df

        df_display = df_filtrado.copy()
        for c in ['Total Gerado (R$)', 'Pontos Expirados (R$)', 'Pontos Resgatados (R$)',
                  'Ajustes (R$)', 'Saldo Disponivel (R$)']:
            df_display[c] = df_display[c].apply(formatar_moeda)

        st.dataframe(df_display, use_container_width=True, hide_index=True)

        st.markdown("---")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.info(f"**Clientes:** {len(df_filtrado)}")
        with col2:
            st.info(f"**Saldo Total:** {formatar_moeda(df_filtrado['Saldo Disponivel (R$)'].sum())}")
        with col3:
            st.info(f"**Resgatado Total:** {formatar_moeda(df_filtrado['Pontos Resgatados (R$)'].sum())}")

        csv_export = df.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            "📥 Exportar (CSV)",
            data=csv_export,
            file_name=f"clientes_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )

        # Detalhe do cliente
        st.markdown("---")
        st.subheader("🔍 Detalhe do Cliente")
        cliente_sel = st.selectbox("Selecione um cliente:", df['Cliente'].tolist())

        if cliente_sel:
            s = calcular_saldo_cliente(cliente_sel)
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Saldo Disponivel", formatar_moeda(s['saldo_disponivel']))
            with col2:
                st.metric("Pontos Ativos", formatar_moeda(s['pontos_ativos']))
            with col3:
                st.metric("Pontos Expirados", formatar_moeda(s['pontos_expirados']))
            with col4:
                st.metric("Pontos Resgatados", formatar_moeda(s['pontos_resgatados']))

            # Vendas do cliente
            with get_conn() as conn:
                df_v = pd.read_sql_query(
                    "SELECT * FROM vendas WHERE cliente = ? ORDER BY data_venda DESC",
                    conn, params=(cliente_sel,)
                )
            if not df_v.empty:
                st.markdown("**Vendas:**")
                hoje = pd.Timestamp.now().normalize()
                df_v['validade_dt'] = pd.to_datetime(df_v['validade'])
                df_v['Situacao'] = df_v.apply(
                    lambda r: '✅ Ativo' if r['validade_dt'] >= hoje else '❌ Expirado', axis=1
                )
                df_v['Pontos'] = df_v['pontos'].apply(formatar_moeda)
                df_v['Valor'] = df_v['valor'].apply(formatar_moeda)
                st.dataframe(
                    df_v[['cupom', 'valor', 'pontos', 'data_venda', 'validade', 'Situacao']].rename(
                        columns={'cupom': 'Cupom', 'valor': 'Valor', 'pontos': 'Pontos',
                                 'data_venda': 'Data', 'validade': 'Validade'}
                    ),
                    use_container_width=True, hide_index=True
                )

            # Resgates do cliente
            with get_conn() as conn:
                df_r = pd.read_sql_query(
                    "SELECT * FROM resgates WHERE cliente = ? ORDER BY id DESC",
                    conn, params=(cliente_sel,)
                )
            if not df_r.empty:
                st.markdown("**Resgates:**")
                df_r['custo_pontos'] = df_r['custo_pontos'].apply(formatar_moeda)
                st.dataframe(
                    df_r[['produto_nome', 'custo_pontos', 'data_resgate', 'status']].rename(
                        columns={'produto_nome': 'Produto', 'custo_pontos': 'Custo',
                                 'data_resgate': 'Data', 'status': 'Status'}
                    ),
                    use_container_width=True, hide_index=True
                )

# ============================================
# PAGINA: RESGATAR PONTOS
# ============================================
elif opcao == "🎁 Resgatar Pontos":
    st.header("🎁 Resgatar Pontos")

    clientes = listar_clientes()
    if not clientes:
        st.warning("Nenhum cliente cadastrado. Faca upload de vendas primeiro.")
    else:
        cliente = st.selectbox("Selecione o cliente:", clientes)

        if cliente:
            s = calcular_saldo_cliente(cliente)

            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("💰 Saldo Disponivel", formatar_moeda(s['saldo_disponivel']))
            with col2:
                st.metric("📈 Pontos Ativos", formatar_moeda(s['pontos_ativos']))
            with col3:
                st.metric("🎁 Resgatados", formatar_moeda(s['pontos_resgatados']))

            if s['saldo_disponivel'] <= 0:
                st.warning("⚠️ Cliente sem saldo disponivel para resgate.")
            else:
                st.markdown("---")
                st.subheader("Produtos Disponiveis")

                produtos = carregar_produtos(somente_ativos=True)
                if produtos.empty:
                    st.info("Nenhum produto cadastrado. Cadastre em 'Gerenciar Produtos'.")
                else:
                    for _, p in produtos.iterrows():
                        estoque_txt = (
                            "Ilimitado" if pd.isna(p['estoque'])
                            else f"{int(p['estoque'])} em estoque"
                        )
                        disponivel = (
                            p['custo_pontos'] <= s['saldo_disponivel']
                            and (pd.isna(p['estoque']) or p['estoque'] > 0)
                        )

                        with st.container(border=True):
                            c1, c2, c3 = st.columns([3, 1, 1])
                            with c1:
                                st.markdown(f"**{p['nome']}**")
                                if p['descricao']:
                                    st.caption(p['descricao'])
                                st.caption(f"Estoque: {estoque_txt}")
                            with c2:
                                st.markdown(f"### {formatar_moeda(p['custo_pontos'])}")
                            with c3:
                                if st.button(
                                    "Resgatar", key=f"resg_{p['id']}",
                                    disabled=not disponivel
                                ):
                                    obs = st.session_state.get(f"obs_{p['id']}", "")
                                    ok, msg = registrar_resgate(cliente, int(p['id']), obs)
                                    if ok:
                                        st.success(msg)
                                        st.rerun()
                                    else:
                                        st.error(msg)

                    # Resgates recentes
                    st.markdown("---")
                    st.subheader("📜 Resgates recentes deste cliente")
                    with get_conn() as conn:
                        df_r = pd.read_sql_query(
                            "SELECT * FROM resgates WHERE cliente = ? ORDER BY id DESC LIMIT 10",
                            conn, params=(cliente,)
                        )
                    if not df_r.empty:
                        df_r['custo_pontos'] = df_r['custo_pontos'].apply(formatar_moeda)
                        st.dataframe(
                            df_r[['produto_nome', 'custo_pontos', 'data_resgate']].rename(
                                columns={'produto_nome': 'Produto', 'custo_pontos': 'Custo',
                                         'data_resgate': 'Data'}
                            ),
                            use_container_width=True, hide_index=True
                        )

# ============================================
# PAGINA: GERENCIAR PRODUTOS
# ============================================
elif opcao == "🛒 Gerenciar Produtos":
    st.header("🛒 Gerenciar Produtos de Resgate")

    with st.expander("➕ Cadastrar novo produto", expanded=False):
        with st.form("form_produto"):
            nome = st.text_input("Nome do produto")
            descricao = st.text_area("Descricao (opcional)")
            custo = st.number_input("Custo em pontos (R$)", min_value=0.01, value=10.0, step=1.0)
            estoque = st.number_input("Estoque (0 = ilimitado)", min_value=0, value=0, step=1)
            submitted = st.form_submit_button("Cadastrar")

            if submitted:
                if not nome.strip():
                    st.error("Informe o nome do produto.")
                else:
                    inserir_produto(
                        nome.strip(), descricao.strip(), float(custo),
                        None if estoque == 0 else int(estoque)
                    )
                    st.success(f"✅ Produto '{nome}' cadastrado.")
                    st.rerun()

    st.markdown("---")
    st.subheader("Produtos Cadastrados")

    produtos = carregar_produtos(somente_ativos=False)
    if produtos.empty:
        st.info("Nenhum produto cadastrado.")
    else:
        for _, p in produtos.iterrows():
            with st.container(border=True):
                c1, c2, c3 = st.columns([3, 1, 1])
                with c1:
                    status = "🟢 Ativo" if p['ativo'] else "🔴 Inativo"
                    st.markdown(f"**{p['nome']}** — {status}")
                    if p['descricao']:
                        st.caption(p['descricao'])
                    estoque_txt = (
                        "Ilimitado" if pd.isna(p['estoque'])
                        else f"{int(p['estoque'])} em estoque"
                    )
                    st.caption(f"Estoque: {estoque_txt}")
                with c2:
                    st.markdown(f"### {formatar_moeda(p['custo_pontos'])}")
                with c3:
                    if st.button("🗑️ Excluir", key=f"del_{p['id']}"):
                        deletar_produto(int(p['id']))
                        st.success("Produto excluido.")
                        st.rerun()

# ============================================
# PAGINA: HISTORICO DE RESGATES
# ============================================
elif opcao == "📜 Historico de Resgates":
    st.header("📜 Historico de Resgates")

    resgates = carregar_resgates()
    if resgates.empty:
        st.info("Nenhum resgate registrado.")
    else:
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total de Resgates", len(resgates))
        with col2:
            st.metric("Pontos Resgatados", formatar_moeda(resgates['custo_pontos'].sum()))
        with col3:
            st.metric("Clientes Atendidos", resgates['cliente'].nunique())

        st.markdown("---")

        clientes = ['Todos'] + sorted(resgates['cliente'].unique().tolist())
        filtro = st.selectbox("Filtrar por cliente:", clientes)
        df_f = resgates if filtro == 'Todos' else resgates[resgates['cliente'] == filtro]

        df_display = df_f.copy()
        df_display['custo_pontos'] = df_display['custo_pontos'].apply(formatar_moeda)
        df_display = df_display[['id', 'data_resgate', 'cliente', 'produto_nome',
                                 'custo_pontos', 'status', 'observacao']]
        df_display.columns = ['ID', 'Data', 'Cliente', 'Produto', 'Custo', 'Status', 'Observacao']

        st.dataframe(df_display, use_container_width=True, hide_index=True)

        csv_export = df_f.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            "📥 Exportar resgates (CSV)",
            data=csv_export,
            file_name=f"resgates_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )

# ============================================
# PAGINA: AJUSTES MANUAIS
# ============================================
elif opcao == "⚙️ Ajustes Manuais":
    st.header("⚙️ Ajustes Manuais de Pontos")
    st.caption("Use para creditar pontos (bonus, correcao) ou debitar (estorno, correcao).")

    clientes = listar_clientes()
    if not clientes:
        st.warning("Nenhum cliente cadastrado.")
    else:
        with st.form("form_ajuste"):
            cliente = st.selectbox("Cliente:", clientes)
            pontos = st.number_input(
                "Pontos (positivo = credito, negativo = debito)",
                value=0.0, step=1.0, format="%.2f"
            )
            motivo = st.text_input("Motivo")
            submitted = st.form_submit_button("Registrar ajuste")

            if submitted:
                if pontos == 0:
                    st.error("Informe um valor diferente de zero.")
                elif not motivo.strip():
                    st.error("Informe o motivo.")
                else:
                    inserir_ajuste(cliente, float(pontos), motivo.strip())
                    st.success(f"✅ Ajuste de {formatar_moeda(pontos)} registrado para {cliente}.")
                    st.rerun()

        st.markdown("---")
        st.subheader("Ajustes Registrados")
        ajustes = carregar_ajustes()
        if ajustes.empty:
            st.info("Nenhum ajuste registrado.")
        else:
            aj = ajustes.copy()
            aj['pontos'] = aj['pontos'].apply(formatar_moeda)
            aj = aj[['id', 'data_ajuste', 'cliente', 'pontos', 'motivo']]
            aj.columns = ['ID', 'Data', 'Cliente', 'Pontos', 'Motivo']
            st.dataframe(aj, use_container_width=True, hide_index=True)

# ============================================
# PAGINA: A EXPIRAR (30 DIAS)
# ============================================
elif opcao == "📅 A Expirar (30 dias)":
    st.header("📅 Pontos a Expirar nos Proximos 30 Dias")

    df = carregar_vendas()
    if df.empty:
        st.warning("Nenhum dado carregado.")
    else:
        hoje = pd.Timestamp.now().normalize()
        df['validade_dt'] = pd.to_datetime(df['validade'])
        df['dias'] = (df['validade_dt'] - hoje).dt.days
        a_expirar = df[(df['dias'] >= 0) & (df['dias'] <= 30)].copy()

        if a_expirar.empty:
            st.success("✅ Nenhum ponto expira nos proximos 30 dias!")
        else:
            st.warning(f"⚠️ {len(a_expirar)} venda(s) com pontos expirando em ate 30 dias")

            d = a_expirar[['cupom', 'cliente', 'valor', 'pontos',
                           'data_venda', 'validade', 'dias']].copy()
            d.columns = ['Cupom', 'Cliente', 'Valor', 'Pontos',
                         'Data Venda', 'Validade', 'Dias p/ Expirar']
            d['Valor'] = d['Valor'].apply(formatar_moeda)
            d['Pontos'] = d['Pontos'].apply(formatar_moeda)
            d = d.sort_values('Dias p/ Expirar')
            st.dataframe(d, use_container_width=True, hide_index=True)

            col1, col2 = st.columns(2)
            with col1:
                st.metric("🎯 Pontos a Expirar", formatar_moeda(a_expirar['pontos'].sum()))
            with col2:
                st.metric("👥 Clientes", a_expirar['cliente'].nunique())

# ============================================
# PAGINA: PONTOS EXPIRADOS
# ============================================
elif opcao == "⚠️ Pontos Expirados":
    st.header("⚠️ Pontos Expirados")

    df = carregar_vendas()
    if df.empty:
        st.warning("Nenhum dado carregado.")
    else:
        hoje = pd.Timestamp.now().normalize()
        df['validade_dt'] = pd.to_datetime(df['validade'])
        expirados = df[df['validade_dt'] < hoje].copy()
        expirados['dias_expirado'] = (hoje - expirados['validade_dt']).dt.days

        if expirados.empty:
            st.success("✅ Nenhum ponto expirado ate o momento!")
        else:
            st.error(f"⚠️ {len(expirados)} venda(s) com pontos expirados")

            d = expirados[['cupom', 'cliente', 'valor', 'pontos',
                           'data_venda', 'validade', 'dias_expirado']].copy()
            d.columns = ['Cupom', 'Cliente', 'Valor', 'Pontos',
                         'Data Venda', 'Validade', 'Dias Expirado']
            d['Valor'] = d['Valor'].apply(formatar_moeda)
            d['Pontos'] = d['Pontos'].apply(formatar_moeda)
            d = d.sort_values('Dias Expirado', ascending=False)
            st.dataframe(d, use_container_width=True, hide_index=True)

            col1, col2 = st.columns(2)
            with col1:
                st.metric("💸 Total Expirado", formatar_moeda(expirados['pontos'].sum()))
            with col2:
                st.metric("👥 Clientes", expirados['cliente'].nunique())

# ============================================
# PAGINA: INFORMACOES
# ============================================
elif opcao == "ℹ️ Informacoes":
    st.header("ℹ️ Informacoes do Sistema")

    st.markdown("## 🎁 Sistema de Bonificacao com Resgate")
    st.markdown("### Regras")
    st.markdown(
        f"- **Taxa:** 1% do valor final da venda\n"
        f"- **Validade:** {DIAS_VALIDADE} dias por venda (individual)\n"
        f"- **Resgate:** troca de pontos por produtos cadastrados\n"
        f"- **Debito automatico:** saldo = ativos + ajustes - resgatados\n"
        f"- **Banco de dados:** `{DB_PATH}` (persistente)"
    )

    st.markdown("### Persistencia Online")
    st.markdown(
        "O sistema usa **SQLite** para persistir os dados. Para usar online:\n"
        "- **Local/VPS:** funciona direto (arquivo `bonificacao.db`)\n"
        "- **Render/Railway:** monte um volume persistente em `/data` e defina "
        "a variavel de ambiente `DB_PATH=/data/bonificacao.db`\n"
        "- **Streamlit Cloud:** use **Supabase** (troque `sqlite3` por `psycopg2`)\n"
        "- **Google Sheets:** alternativa via `gspread`"
    )

    st.markdown("### Abas do Sistema")
    st.markdown(
        "- **📤 Upload:** processa CSV e acumula no banco\n"
        "- **📊 Dashboard:** metricas gerais\n"
        "- **👥 Clientes:** saldo por cliente + detalhe\n"
        "- **🎁 Resgatar Pontos:** interface de resgate\n"
        "- **🛒 Gerenciar Produtos:** CRUD de produtos\n"
        "- **📜 Historico de Resgates:** auditoria\n"
        "- **⚙️ Ajustes Manuais:** creditos/debitos\n"
        "- **📅 A Expirar:** pontos vencendo em 30 dias\n"
        "- **⚠️ Pontos Expirados:** pontos ja vencidos"
    )

# ============================================
# RODAPE
# ============================================
st.markdown("---")
st.markdown(
    "<div style='text-align: center; color: gray;'>"
    "Sistema de Bonificacao v3.0 | Desenvolvido com Streamlit + SQLite"
    "</div>",
    unsafe_allow_html=True
)
