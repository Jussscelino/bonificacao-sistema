import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, timedelta

# Configuração da interface
st.set_page_config(page_title="Casa da Construção - Bonificação", layout="wide")

# Conexão com o banco de dados SQLite
def get_connection():
    # check_same_thread=False é necessário no Streamlit para evitar erros de threading
    conn = sqlite3.connect('bonificacao.db', check_same_thread=False)
    return conn

# Criação da tabela caso não exista
def init_db():
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS vendas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente TEXT,
            data_venda DATE,
            valor_gasto REAL,
            bonus_gerado REAL
        )
    ''')
    conn.commit()

init_db()

st.title("Sistema de Bonificação de Clientes")
st.write("Cada R$ 1,00 em compras gera R$ 0,01 em bônus (1%). Os pontos expiram em 365 dias.")

# Criação de abas para organizar o painel
tab1, tab2 = st.tabs(["Painel de Clientes", "Upload de CSV Mensal"])

with tab2:
    st.header("Importar Vendas do Mês")
    st.markdown("**Formato exigido do CSV:** Colunas nomeadas como `Data` (formato YYYY-MM-DD), `Cliente` e `Valor`.")
    
    uploaded_file = st.file_uploader("Selecione o arquivo CSV gerado pelo seu sistema", type=['csv'])

    if uploaded_file is not None:
        try:
            df = pd.read_csv(uploaded_file)
            
            # Verifica se as colunas necessárias existem
            if all(col in df.columns for col in ['Data', 'Cliente', 'Valor']):
                conn = get_connection()
                
                # Regra de negócio: 1% de bonificação
                df['bonus_gerado'] = df['Valor'] * 0.01

                # Inserção no banco de dados
                linhas_inseridas = 0
                for _, row in df.iterrows():
                    conn.execute(
                        "INSERT INTO vendas (cliente, data_venda, valor_gasto, bonus_gerado) VALUES (?, ?, ?, ?)",
                        (row['Cliente'], row['Data'], row['Valor'], row['bonus_gerado'])
                    )
                    linhas_inseridas += 1
                
                conn.commit()
                st.success(f"Sucesso! {linhas_inseridas} registros foram importados para o banco de dados.")
            else:
                st.error("Erro: O arquivo CSV precisa conter exatamente as colunas: 'Data', 'Cliente' e 'Valor'.")
        except Exception as e:
            st.error(f"Erro ao processar o arquivo: {e}")

with tab1:
    st.header("Saldo Ativo de Bonificações")
    
    conn = get_connection()

    # Regra de negócio: validade de 1 ano (365 dias)
    data_corte = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')

    # A query soma os valores apenas de datas posteriores à data de corte
    query = f"""
        SELECT 
            cliente as Cliente, 
            SUM(valor_gasto) as Total_Gasto_12_Meses, 
            SUM(bonus_gerado) as Bonus_Disponivel 
        FROM vendas 
        WHERE data_venda >= '{data_corte}' 
        GROUP BY cliente 
        HAVING Bonus_Disponivel > 0 
        ORDER BY Bonus_Disponivel DESC
    """

    try:
        df_saldos = pd.read_sql_query(query, conn)

        if not df_saldos.empty:
            # Formatação visual para moeda (R$)
            df_saldos['Total_Gasto_12_Meses'] = df_saldos['Total_Gasto_12_Meses'].apply(lambda x: f"R$ {x:,.2f}".replace(',','_').replace('.',',').replace('_','.'))
            df_saldos['Bonus_Disponivel'] = df_saldos['Bonus_Disponivel'].apply(lambda x: f"R$ {x:,.2f}".replace(',','_').replace('.',',').replace('_','.'))

            # Exibe a tabela na tela
            st.dataframe(df_saldos, use_container_width=True, hide_index=True)
            
            st.metric(label="Clientes com Bônus Ativo", value=len(df_saldos))
        else:
            st.info("Nenhum bônus ativo no período de 1 ano.")
    except Exception as e:
        st.info("O banco de dados está vazio. Faça o upload do primeiro CSV.")