import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
import glob

files = glob.glob('results/*.csv')
df = pd.concat([pd.read_csv(f) for f in files])

plt.figure(figsize=(12, 8))
sns.boxplot(x='algorithm', y='completion_time', data=df)
plt.title('Время распространения информации по алгоритмам')
plt.ylabel('Время (сек)')
plt.savefig('results/comparison_by_algorithm.png')

gossip_df = df[df['algorithm'] == 'gossip']
plt.figure(figsize=(12, 8))
sns.lineplot(x='loss_prob', y='completion_time', 
             hue='gossip_mode', style='adaptive',
             data=gossip_df, markers=True)
plt.title('Влияние потерь пакетов на Gossip')
plt.savefig('results/packet_loss_impact.png')

plt.figure(figsize=(12, 8))
sns.lineplot(x='broken_prob', y='coverage_100pct', 
             hue='gossip_mode', data=gossip_df)
plt.title('Влияние сбоев узлов на распространение')
plt.savefig('results/node_failures_impact.png')