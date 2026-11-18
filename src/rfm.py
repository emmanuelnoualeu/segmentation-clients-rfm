"""
Segmentation clients RFM et analyse de rétention par cohortes.

    python src/telecharger_donnees.py
    python src/rfm.py
"""
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick

RACINE = Path(__file__).resolve().parents[1]
BLEU, ORANGE, AQUA, JAUNE, MAGENTA, VERT, VIOLET, ROUGE = (
    "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948")
INK, INK2, GRILLE, GRIS = "#0b0b0b", "#52514e", "#e6e5e1", "#a3a29c"
plt.rcParams.update({"axes.spines.top": False, "axes.spines.right": False, "font.size": 10,
                     "axes.edgecolor": INK2, "axes.labelcolor": INK2, "xtick.color": INK2,
                     "ytick.color": INK2, "axes.titleweight": "bold", "axes.titlelocation": "left",
                     "axes.titlesize": 11})
CODES_NON_PRODUIT = r"^(POST|DOT|M|D|S|C2|BANK CHARGES|AMAZONFEE|CRUK|PADS|B|m|gift_.*|DCGS.*)$"


# ---------------------------------------------------------------- nettoyage
def nettoyer(chemin):
    d = pd.read_csv(chemin, dtype={"InvoiceNo": str, "StockCode": str, "CustomerID": "float"})
    journal = [("Lignes brutes", len(d))]
    d = d.drop_duplicates();                                  journal.append(("Doublons exacts supprimés", len(d)))
    d = d[~d.InvoiceNo.str.startswith("C")];                  journal.append(("Factures d'annulation retirées", len(d)))
    d = d[(d.Quantity > 0) & (d.UnitPrice > 0)];              journal.append(("Quantités/prix nuls ou négatifs retirés", len(d)))
    d = d[~d.StockCode.str.match(CODES_NON_PRODUIT)];         journal.append(("Frais de port, remises, frais bancaires retirés", len(d)))
    ventes_sans_client = d.CustomerID.isna()
    ca_sans_client = (d.Quantity * d.UnitPrice)[ventes_sans_client].sum()
    d = d[~ventes_sans_client];                               journal.append(("Lignes sans identifiant client retirées", len(d)))
    d["InvoiceDate"] = pd.to_datetime(d.InvoiceDate, format="%m/%d/%Y %H:%M")
    d["montant"] = d.Quantity * d.UnitPrice
    d["CustomerID"] = d.CustomerID.astype(int)
    return d, pd.DataFrame(journal, columns=["Étape", "Lignes restantes"]), ca_sans_client


# --------------------------------------------------------------------- RFM
SEGMENTS = [  # (nom, condition sur scores R et F), évaluées dans l'ordre
    ("Champions",            lambda r, f: (r >= 4) & (f >= 4)),
    ("Clients fidèles",      lambda r, f: (r >= 3) & (f >= 4)),
    ("Fidèles en devenir",   lambda r, f: (r >= 4) & (f >= 2)),
    ("Nouveaux clients",     lambda r, f: (r >= 4) & (f == 1)),
    ("À surveiller",         lambda r, f: (r == 3) & (f <= 3)),
    ("À risque",             lambda r, f: (r <= 2) & (f >= 3)),
    ("En hibernation",       lambda r, f: (r == 2) & (f <= 2)),
    ("Perdus",               lambda r, f: (r == 1) & (f <= 2)),
]
ORDRE = [s[0] for s in SEGMENTS]
COUL_SEG = dict(zip(ORDRE, [BLEU, AQUA, VERT, VIOLET, JAUNE, ORANGE, MAGENTA, ROUGE]))


def rfm(d):
    ref = d.InvoiceDate.max().normalize() + pd.Timedelta(days=1)
    t = d.groupby("CustomerID").agg(
        recence=("InvoiceDate", lambda x: (ref - x.max()).days),
        frequence=("InvoiceNo", "nunique"),
        montant=("montant", "sum"),
        pays=("Country", "first"))
    # Quintiles ; rang pour départager les ex-æquo de fréquence (beaucoup de clients à 1 commande)
    t["R"] = pd.qcut(t.recence.rank(method="first"), 5, labels=[5, 4, 3, 2, 1]).astype(int)
    t["F"] = pd.qcut(t.frequence.rank(method="first"), 5, labels=[1, 2, 3, 4, 5]).astype(int)
    t["M"] = pd.qcut(t.montant.rank(method="first"), 5, labels=[1, 2, 3, 4, 5]).astype(int)
    t["segment"] = np.select([c(t.R, t.F) for _, c in SEGMENTS], ORDRE, default="Autres")
    return t, ref


def synthese_segments(t):
    s = t.groupby("segment").agg(clients=("R", "size"), recence_mediane=("recence", "median"),
                                 commandes_moy=("frequence", "mean"), ca=("montant", "sum"),
                                 panier_client_median=("montant", "median"))
    s["part_clients_pct"] = 100 * s.clients / s.clients.sum()
    s["part_ca_pct"] = 100 * s.ca / s.ca.sum()
    return s.reindex([x for x in ORDRE if x in s.index]).round(1)


# ----------------------------------------------------------------- cohortes
def cohortes(d):
    # Décembre 2011 n'a que 9 jours de données : on l'exclut pour ne pas sous-estimer la dernière diagonale
    x = d.loc[d.InvoiceDate < "2011-12-01", ["CustomerID", "InvoiceDate"]].copy()
    x["mois"] = x.InvoiceDate.dt.to_period("M")
    x["cohorte"] = x.groupby("CustomerID").mois.transform("min")
    x["age"] = (x.mois - x.cohorte).apply(lambda p: p.n)
    tab = x.groupby(["cohorte", "age"]).CustomerID.nunique().unstack()
    taux = tab.div(tab[0], axis=0) * 100
    return taux, tab[0]


# ------------------------------------------------------------------ figures
def fig_segments(s, chemin):
    s = s.sort_values("part_ca_pct")
    fig, ax = plt.subplots(figsize=(9.5, 4.6))
    y = np.arange(len(s))
    ax.barh(y + 0.2, s.part_clients_pct, height=0.38, color=GRIS, label="Part des clients")
    ax.barh(y - 0.2, s.part_ca_pct, height=0.38, color=[COUL_SEG[i] for i in s.index], label="Part du chiffre d'affaires")
    for i, (pc, pca) in enumerate(zip(s.part_clients_pct, s.part_ca_pct)):
        ax.text(pca + 0.6, i - 0.2, f"{pca:.0f} %", va="center", fontsize=8.5, color=INK)
        ax.text(pc + 0.6, i + 0.2, f"{pc:.0f} %", va="center", fontsize=8, color=INK2)
    ax.set_yticks(y, s.index)
    ax.xaxis.set_major_formatter(mtick.PercentFormatter(decimals=0))
    ax.xaxis.grid(True, color=GRILLE); ax.set_axisbelow(True)
    top = s.loc["Champions"]
    ax.set_title(f"Les Champions : {top.part_clients_pct:.0f} % des clients, {top.part_ca_pct:.0f} % du chiffre d'affaires")
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(color=GRIS, label="Part des clients"), Patch(color=BLEU, label="Part du CA (couleur du segment)")],
              frameon=False, fontsize=8.5, loc="lower right")
    fig.tight_layout(); fig.savefig(chemin, dpi=170); plt.close(fig)


def fig_pareto(t, chemin):
    m = t.montant.sort_values(ascending=False).values
    cum = np.cumsum(m) / m.sum() * 100
    x = np.arange(1, len(m) + 1) / len(m) * 100
    i20 = np.searchsorted(x, 20)
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    ax.plot(x, cum, color=BLEU, lw=2.2)
    ax.plot([0, 100], [0, 100], color=GRIS, lw=1, ls=":")
    ax.scatter([x[i20]], [cum[i20]], s=40, color=ORANGE, zorder=3, edgecolor="white", linewidth=1.5)
    ax.annotate(f"20 % des clients\n= {cum[i20]:.0f} % du CA", (x[i20], cum[i20]), xytext=(32, 55),
                fontsize=9, color=INK, arrowprops=dict(arrowstyle="-", color=INK2, lw=0.8))
    ax.set_xlabel("Part cumulée des clients, du plus gros au plus petit")
    ax.set_ylabel("Part cumulée du CA")
    for a in (ax.xaxis, ax.yaxis):
        a.set_major_formatter(mtick.PercentFormatter(decimals=0))
    ax.grid(True, color=GRILLE); ax.set_axisbelow(True)
    ax.set_title("Concentration du chiffre d'affaires (courbe de Pareto)")
    fig.tight_layout(); fig.savefig(chemin, dpi=170); plt.close(fig)


def fig_cohortes(taux, tailles, chemin):
    taux = taux[taux.iloc[:, 1].notna()]
    v = taux.iloc[:, 1:].values
    fig, ax = plt.subplots(figsize=(11, 5.4))
    im = ax.imshow(v, cmap="Blues", vmin=0, vmax=50, aspect="auto")
    MOIS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]
    lab = [f"{MOIS[p.month - 1]} {p.year} · {int(tailles[p])} clients" + (" *" if i == 0 else "")
           for i, p in enumerate(taux.index)]
    ax.set_yticks(range(len(lab)), lab, fontsize=8.5)
    ax.set_xticks(range(v.shape[1]), [f"M+{i}" for i in range(1, v.shape[1] + 1)], fontsize=8.5)
    for s_ in ax.spines.values():
        s_.set_visible(False)
    for i in range(v.shape[0]):
        for j in range(v.shape[1]):
            if not np.isnan(v[i, j]):
                ax.text(j, i, f"{v[i, j]:.0f}", ha="center", va="center", fontsize=7.5,
                        color="white" if v[i, j] > 30 else INK)
    ax.set_xlabel("Mois après le premier achat    (* début des données : inclut des clients plus anciens)")
    ax.set_ylabel("Cohorte (nouveaux clients)")
    ax.set_title("Rétention par cohorte : moins d'un nouveau client sur quatre revient le mois suivant")
    fig.colorbar(im, ax=ax, shrink=0.8, label="% de clients actifs")
    fig.tight_layout(); fig.savefig(chemin, dpi=170); plt.close(fig)


def fig_mensuel(d, chemin):
    m = d.set_index("InvoiceDate").montant.resample("MS").sum() / 1000
    m = m[m.index < "2011-12-01"]
    fig, ax = plt.subplots(figsize=(9, 3.6))
    ax.bar(m.index, m.values, width=20, color=[ORANGE if x.month in (9, 10, 11) else BLEU for x in m.index])
    ax.set_ylabel("CA (milliers £)")
    ax.yaxis.grid(True, color=GRILLE); ax.set_axisbelow(True)
    import matplotlib.dates as mdates
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%y"))
    pct = 100 * m[m.index.month.isin([9, 10, 11])].sum() / m.sum()
    ax.set_title(f"Septembre à novembre font {pct:.0f} % du CA annuel : la saison des commandes de Noël")
    fig.tight_layout(); fig.savefig(chemin, dpi=170); plt.close(fig)


def main():
    d, journal, ca_sans_client = nettoyer(RACINE / "data/online_retail.csv")
    print(journal.to_string(index=False))
    print(f"CA sur lignes sans client (exclu de la segmentation) : {ca_sans_client:,.0f} £")
    journal.to_csv(RACINE / "resultats/journal_nettoyage.csv", index=False)
    t, ref = rfm(d)
    t.to_csv(RACINE / "resultats/scores_rfm_par_client.csv")
    s = synthese_segments(t)
    s.to_csv(RACINE / "resultats/synthese_segments.csv")
    print(f"\n{len(t)} clients, référence {ref.date()}, CA {t.montant.sum():,.0f} £\n", s.to_string())
    m = t.montant.sort_values(ascending=False)
    print(f"Top 20 % des clients = {100 * m.iloc[:int(.2 * len(m))].sum() / m.sum():.1f} % du CA")
    print("Clients à une seule commande :", f"{100 * (t.frequence == 1).mean():.1f} %")
    taux, tailles = cohortes(d)
    taux.round(1).to_csv(RACINE / "resultats/retention_cohortes.csv")
    print("Rétention M+1 moyenne (hors déc. 2010) :", round(taux.iloc[1:, 1].mean(), 1), "% ; déc. 2010 M+1 :", round(taux.iloc[0, 1], 1))
    print("Rétention M+3 moyenne (hors déc. 2010) :", round(taux.iloc[1:, 3].mean(), 1))
    print("Pays hors R-U, part du CA :", round(100 * d[d.Country != "United Kingdom"].montant.sum() / d.montant.sum(), 1))
    fig_mensuel(d, RACINE / "figures/01_ca_mensuel.png")
    fig_segments(s, RACINE / "figures/02_segments_rfm.png")
    fig_pareto(t, RACINE / "figures/03_pareto.png")
    fig_cohortes(taux, tailles, RACINE / "figures/04_cohortes.png")


if __name__ == "__main__":
    main()
