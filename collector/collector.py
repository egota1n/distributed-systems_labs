import pika
import os
import json
import time
from datetime import datetime

class MetricsCollector:
    def __init__(self):
        self.total_nodes = int(os.getenv('TOTAL_NODES', 100))
        self.rabbitmq_host = os.getenv('RABBITMQ_HOST', 'rabbitmq')
        self.received_messages = {}
        self.completion_times = {}
        self.setup_rabbitmq()

    def setup_rabbitmq(self):
        credentials = pika.PlainCredentials('admin', 'admin')
        parameters = pika.ConnectionParameters(
            host=self.rabbitmq_host,
            credentials=credentials
        )
        connection = pika.BlockingConnection(parameters)
        
        channel = connection.channel()
        channel.queue_declare(queue='metrics')
        
        channel.basic_consume(
            queue='metrics',
            on_message_callback=self.handle_metric,
            auto_ack=True
        )
        
        print("Collector started. Waiting for metrics...")
        channel.start_consuming()

    def handle_metric(self, ch, method, properties, body):
        try:
            metric = json.loads(body)
            message_id = metric['message_id']
            node_id = metric['node_id']
            action = metric['action']
            
            if message_id not in self.received_messages:
                self.received_messages[message_id] = {
                    'initiated': None,
                    'received': set()
                }
            
            if action == 'initiated':
                self.received_messages[message_id]['initiated'] = metric['timestamp']
            
            elif action == 'received':
                self.received_messages[message_id]['received'].add(node_id)
                
                if len(self.received_messages[message_id]['received']) == self.total_nodes - 1:
                    initiated = datetime.fromisoformat(self.received_messages[message_id]['initiated'])
                    completed = datetime.fromisoformat(metric['timestamp'])
                    latency = (completed - initiated).total_seconds()
                    
                    self.completion_times[message_id] = {
                        'algorithm': metric['algorithm'],
                        'latency': latency,
                        'total_nodes': self.total_nodes
                    }
                    
                    self.save_results()
            
        except Exception as e:
            print(f"Error processing metric: {e}")

    def save_results(self):
        with open('/results/results.json', 'w') as f:
            json.dump(self.completion_times, f, indent=2)
        print("Results updated")

if __name__ == "__main__":
    collector = MetricsCollector()