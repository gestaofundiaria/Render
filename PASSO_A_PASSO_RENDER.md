# Publicação no Render

## 1. Enviar o projeto para o GitHub
No terminal, dentro da pasta do projeto:

```powershell
git init
git add .
git commit -m "Preparar deploy no Render"
git branch -M main
git remote add origin https://github.com/SEU-USUARIO/SEU-REPOSITORIO.git
git push -u origin main
```

## 2. Criar a conta no Render
- Acesse: https://render.com/
- Entre com GitHub

## 3. Publicar usando o `render.yaml`
- Clique em **New +**
- Escolha **Blueprint**
- Selecione o repositório enviado ao GitHub
- Confirme a criação do serviço

O Render vai ler automaticamente:
- `requirements.txt`
- `render.yaml`

## 4. Esperar o deploy
Após alguns minutos, o Render vai gerar uma URL pública parecida com:

```text
https://gestao-fundiaria.onrender.com
```

## 5. Testar
- Abra a URL pública
- Faça login com um dos usuários cadastrados no `app.py`
- Verifique se o mapa e o `teste.geojson` carregam normalmente

## 6. Atualizar depois
Sempre que alterar o projeto:

```powershell
git add .
git commit -m "Atualização do mapa"
git push
```

O Render fará novo deploy automaticamente.

## Observações
- O serviço gratuito pode demorar alguns segundos para "acordar"
- Para mais segurança, troque as senhas fracas no `app.py`
- O segredo de sessão (`GESTORES_SECRET_KEY`) já fica preparado para ser gerado no Render
