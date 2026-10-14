 meu-app — GitOps com kind, ArgoCD e GitHub Actions

Pipeline completo de entrega contínua: cada commit na branch `main` gera uma nova imagem, atualiza o manifest Kubernetes e é implantado automaticamente no cluster pelo ArgoCD — sem nenhum `kubectl apply` manual.

![CI](https://github.com/Jacksonmaarinho/meu-app/actions/workflows/ci.yaml/badge.svg)

## Arquitetura

```
 developer                GitHub                              EC2 (Amazon Linux)
 ─────────                ──────                              ──────────────────
 git push ──► main ──► GitHub Actions ──► GHCR (imagem:sha)
                            │
                            └──► commit "deploy: <sha>" em k8s/deployment.yaml
                                        │
                                        ▼
                                   ArgoCD (polling) ──► kind cluster ──► Deployment (3 réplicas)
                                   auto-sync · prune · selfHeal         Service (ClusterIP)
```

| Camada | Ferramenta | Função |
|---|---|---|
| Infraestrutura | EC2 Amazon Linux 2023 + kind | Cluster Kubernetes em um único nó |
| Aplicação | Python / Flask + Docker | Serviço HTTP mínimo (`GET /`) |
| Registry | GitHub Container Registry (GHCR) | Imagens versionadas pelo SHA do commit |
| CI | GitHub Actions | Build, push e atualização do manifest |
| CD | ArgoCD | Sincroniza o cluster com o Git (fonte da verdade) |

## Estrutura do repositório

```
.
├── app/
│   ├── main.py              # aplicação Flask
│   ├── requirements.txt
│   └── Dockerfile
├── k8s/
│   ├── deployment.yaml      # tag da imagem atualizada pela CI
│   └── service.yaml
├── argocd-app.yaml          # Application do ArgoCD (auto-sync)
└── .github/workflows/
    └── ci.yaml              # pipeline de build e deploy
```

## Fluxo de deploy

1. Um commit altera algo em `app/**` na branch `main`.
2. O workflow `CI` constrói a imagem e publica em `ghcr.io/jacksonmaarinho/meu-app:<sha>`.
3. O próprio workflow altera a tag em `k8s/deployment.yaml` e faz um commit `deploy: <sha>`.
4. O ArgoCD detecta a diferença entre o Git e o cluster e aplica a mudança.
5. O Deployment faz rolling update para a nova imagem.

O filtro `paths: ["app/**"]` garante que o commit feito pela CI (que só toca `k8s/`) não dispare o pipeline novamente.

## Decisões de arquitetura

- **Tag = SHA do commit.** Cada imagem é rastreável até a linha de código que a gerou; nada de `latest` em produção.
- **ArgoCD com `prune` e `selfHeal`.** Recursos removidos do Git são removidos do cluster; alterações manuais (`kubectl scale`, por exemplo) são revertidas automaticamente.
- **Configuração do ArgoCD versionada.** O `argocd-app.yaml` vive no repositório, não foi criado pela UI.
- **kind em EC2 em vez de EKS.** Atende ao escopo de "cluster local" com custo mínimo (`t3.medium`), mantendo o mesmo repositório pronto para migrar para EKS sem alterações.

## Como reproduzir

### Pré-requisitos

- VM Linux com pelo menos 4 GB de RAM (ex.: EC2 `t3.medium`, Amazon Linux 2023)
- Docker, `kubectl`, `kind` e `git`
- Conta no GitHub com **Settings → Actions → Workflow permissions → Read and write**

### 1. Cluster

```bash
kind create cluster --name gitops
kubectl get nodes
```

### 2. ArgoCD

```bash
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
kubectl wait -n argocd --for=condition=available deploy/argocd-server --timeout=300s

# senha inicial do usuário admin
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d; echo
```

Acesso à UI a partir da máquina local (túnel SSH):

```bash
# na VM
kubectl port-forward svc/argocd-server -n argocd 8081:443 > /dev/null 2>&1 &

# na máquina local
ssh -i chave.pem -L 8081:localhost:8081 ec2-user@IP_DA_VM
# depois abra https://localhost:8081
```

### 3. Registrar a aplicação

```bash
kubectl apply -f argocd-app.yaml
kubectl get application -n argocd   # esperado: Synced / Healthy
```

### 4. Testar o pipeline

```bash
sed -i 's/Hello GitOps v2/Hello GitOps v3/' app/main.py
git commit -am "feat: v3" && git push
```

Acompanhe em **Actions**; em seguida o ArgoCD aplica a nova imagem (até 3 minutos, ou clique em *Refresh* na UI).

```bash
kubectl port-forward svc/meu-app 8080:80 > /dev/null 2>&1 &
curl localhost:8080   # Hello GitOps v3
```

> A imagem no GHCR nasce privada. Na primeira execução, torne o pacote público em **Profile → Packages → meu-app → Package settings → Change visibility**, ou crie um `imagePullSecret` no cluster.

## Validações realizadas

- **Mudança via Git:** alterar `replicas: 2 → 3` no manifest e fazer push resultou em um terceiro pod sem intervenção manual.
- **Self-heal:** `kubectl scale deploy meu-app --replicas=1` foi revertido pelo ArgoCD em segundos.
- **Deploy automático:** commit em `app/main.py` → pipeline verde → `curl` respondendo a nova versão.

## Próximos passos

- Kustomize com overlays `dev` / `prod`
- Webhook GitHub → ArgoCD para sync instantâneo
- ArgoCD Image Updater no lugar do `sed` na CI
- Migração para EKS mantendo o mesmo repositório

## Licença

MIT
