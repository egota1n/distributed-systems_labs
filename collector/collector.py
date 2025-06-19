import pika
import os
import json
import time
import csv
from datetime import datetime
from collections import defaultdict

class MetricsCollector:
    def __init__(self):
        self.total_nodes = int(os.getenv('TOTAL_NODES', 100))
        self.rabbitmq_host = os.getenv('RABBITMQ_HOST', 'rabbitmq')
        self.received_messages = {}
        self.completion_times = {}
        self.coverage_data = defaultdict(dict)
        self.packet_loss = defaultdict(int)
        self.setup_rabbitmq()
        self.start_time = time.time()
        
        os.makedirs('/results', exist_ok=True)
        self.results_file = f"/results/results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        self.init_results_file()

    def init_results_file(self):
        with open(self.results_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                'message_id', 'algorithm', 'gossip_mode', 'adaptive', 
                'gossip_k', 'loss_prob', 'broken_prob', 
                'initiated_at', 'first_received', 'completion_time', 
                'total_nodes', 'coverage_50pct', 'coverage_90pct', 'coverage_100pct',
                'packet_loss_count', 'node_failures'
            ])

    def setup_rabbitmq(self):
        credentials = pika.PlainCredentials('admin', 'admin')
        parameters = pika.ConnectionParameters(
            host=self.rabbitmq_host,
            port=5672,
            virtual_host='/',
            credentials=credentials,
            connection_attempts=10,
            retry_delay=5,
            socket_timeout=10
        )
        
        print(f"Connecting to RabbitMQ at {self.rabbitmq_host}...")
        
        for attempt in range(1, 11):
            try:
                connection = pika.BlockingConnection(parameters)
                self.channel = connection.channel()
                self.channel.queue_declare(queue='metrics')
                print("✅ Successfully connected to RabbitMQ")
                return
            except Exception as e:
                print(f"❌ Connection failed (attempt {attempt}/10): {e}")
                time.sleep(5)
        
        raise Exception("Failed to connect to RabbitMQ after 10 attempts")

    def handle_metric(self, ch, method, properties, body):
        try:
            metric = json.loads(body)
            message_id = metric['message_id']
            node_id = metric['node_id']
            action = metric['action']
            timestamp = datetime.fromisoformat(metric['timestamp'])
            
            if message_id not in self.received_messages:
                self.received_messages[message_id] = {
                    'initiated': timestamp,
                    'first_received': None,
                    'received': set(),
                    'algorithm': metric['algorithm'],
                    'gossip_mode': metric.get('gossip_mode', ''),
                    'adaptive': metric.get('adaptive', False),
                    'gossip_k': metric.get('gossip_k', 0),
                    'loss_prob': metric.get('loss_prob', 0.0),
                    'broken_prob': metric.get('broken', 0.0)
                }
            
            if action == 'initiated':
                self.received_messages[message_id]['initiated'] = timestamp
                print(f"Message {message_id} initiated at {timestamp}")
            
            elif action == 'received':
                if self.received_messages[message_id]['first_received'] is None:
                    self.received_messages[message_id]['first_received'] = timestamp
                    first_delay = (timestamp - self.received_messages[message_id]['initiated']).total_seconds()
                    print(f"First received {message_id} at node {node_id} after {first_delay:.2f}s")
                
                self.received_messages[message_id]['received'].add(node_id)
                received_count = len(self.received_messages[message_id]['received'])
                
                coverage = received_count / self.total_nodes
                self.coverage_data[message_id][timestamp] = coverage
                
                if received_count == self.total_nodes - 1:
                    initiated = self.received_messages[message_id]['initiated']
                    completed = timestamp
                    latency = (completed - initiated).total_seconds()
                    
                    coverage_50 = self.calculate_coverage_time(message_id, 0.5)
                    coverage_90 = self.calculate_coverage_time(message_id, 0.9)
                    
                    result = {
                        'message_id': message_id,
                        'algorithm': self.received_messages[message_id]['algorithm'],
                        'gossip_mode': self.received_messages[message_id]['gossip_mode'],
                        'adaptive': self.received_messages[message_id]['adaptive'],
                        'gossip_k': self.received_messages[message_id]['gossip_k'],
                        'loss_prob': self.received_messages[message_id]['loss_prob'],
                        'broken_prob': self.received_messages[message_id]['broken_prob'],
                        'initiated_at': initiated.isoformat(),
                        'first_received': self.received_messages[message_id]['first_received'].isoformat(),
                        'completion_time': latency,
                        'total_nodes': self.total_nodes,
                        'coverage_50pct': coverage_50,
                        'coverage_90pct': coverage_90,
                        'coverage_100pct': latency,
                        'packet_loss_count': self.packet_loss.get(message_id, 0),
                        'node_failures': sum(1 for msg in self.received_messages.values() if msg.get('broken_prob', 0) > 0)
                    }
                    
                    self.save_result(result)
                    print(f"✅ Message {message_id} completed in {latency:.2f}s")
            
            elif action == 'packet_loss':
                self.packet_loss[message_id] = self.packet_loss.get(message_id, 0) + 1
            
            elif action == 'node_broken':
                print(f"⚠️ Node {node_id} is broken")
            
        except Exception as e:
            print(f"Error processing metric: {e}")

    def calculate_coverage_time(self, message_id, target_coverage):
        if not self.coverage_data[message_id]:
            return 0
        
        sorted_times = sorted(self.coverage_data[message_id].items())
        initiated = self.received_messages[message_id]['initiated']
        
        for timestamp, coverage in sorted_times:
            if coverage >= target_coverage:
                return (timestamp - initiated).total_seconds()
        
        return 0

    def save_result(self, result):
        with open('/results/results.json', 'a') as f:
            f.write(json.dumps(result) + '\n')
        
        with open(self.results_file, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                result['message_id'],
                result['algorithm'],
                result['gossip_mode'],
                result['adaptive'],
                result['gossip_k'],
                result['loss_prob'],
                result['broken_prob'],
                result['initiated_at'],
                result['first_received'],
                result['completion_time'],
                result['total_nodes'],
                result['coverage_50pct'],
                result['coverage_90pct'],
                result['coverage_100pct'],
                result['packet_loss_count'],
                result['node_failures']
            ])
        
        print(f"Results saved for {result['message_id']}")

if __name__ == "__main__":
    collector = MetricsCollector()