# 👉 AJOUT UNIQUEMENT CETTE PARTIE À LA FIN DU BLOC SIMULATION

        # =========================
        # 📤 EXPORT EXCEL XML (AJOUT)
        # =========================

        def df_to_excel_xml(df):
            xml = '<?xml version="1.0"?>\n'
            xml += '<?mso-application progid="Excel.Sheet"?>\n'
            xml += '<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"\n'
            xml += ' xmlns:o="urn:schemas-microsoft-com:office:office"\n'
            xml += ' xmlns:x="urn:schemas-microsoft-com:office:excel"\n'
            xml += ' xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">\n'

            xml += '<Worksheet ss:Name="Simulation">\n<Table>\n'

            # colonnes
            xml += '<Row>\n'
            for col in df.columns:
                xml += f'<Cell><Data ss:Type="String">{col}</Data></Cell>\n'
            xml += '</Row>\n'

            # données
            for _, row in df.iterrows():
                xml += '<Row>\n'
                for val in row:
                    xml += f'<Cell><Data ss:Type="String">{val}</Data></Cell>\n'
                xml += '</Row>\n'

            xml += '</Table>\n</Worksheet>\n</Workbook>'

            return xml

        xml_data = df_to_excel_xml(df)

        st.download_button(
            label="📥 Télécharger Excel (XML)",
            data=xml_data,
            file_name="simulation_p10.xml",
            mime="application/xml"
        )
