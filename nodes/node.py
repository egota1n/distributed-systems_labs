import pika
import os
import json
import time
import random
import threading
from datetime import datetime

class DistributedNode:
    def __init__(self):
        self.node_id = os.getenv('NODE_ID')
        self.total_nodes = int(os.getenv('TOTAL_NODES', 100))
        self.algorithm = os.getenv('ALGORITHM', 'gossip')
        self.loss_prob = float(os.getenv('LOSS_PROBABILITY', 0.0))
        self.gossip_k = int(os.getenv('GOSSIP_K', 3))
        self.broken = random.random() < float(os.getenv('BROKEN_PROBABILITY', 0.0))
        self.rabbitmq_host = os.getenv('RABBITMQ_HOST', 'rabbitmq')
        
        self.received_messages = set()
        self.start_time = time.time()
        self.connection = None
        self.channel = None
        self.setup_rabbitmq()

    def setup_rabbitmq(self):
        credentials = pika.PlainCredentials('admin', 'admin')
        parameters = pika.ConnectionParameters(
            host=os.getenv('RABBITMQ_HOST', 'rabbitmq'),
            port=5672,
            credentials=credentials,
            connection_attempts=10,
            retry_delay=5
        )
        self.connection = pika.BlockingConnection(parameters)

        self.channel = self.connection.channel()
        
        self.channel.queue_declare(queue=f'node_{self.node_id}')
        
        self.channel.exchange_declare(exchange='broadcast', exchange_type='fanout')
        self.channel.exchange_declare(exchange='multicast', exchange_type='topic')
        
        self.channel.queue_bind(exchange='broadcast', queue=f'node_{self.node_id}')
        
        self.channel.queue_declare(queue='metrics')

    def send_metrics(self, message_id, action):
        metrics = {
            'node_id': self.node_id,
            'message_id': message_id,
            'action': action,
            'timestamp': datetime.utcnow().isoformat(),
            'algorithm': self.algorithm
        }
        self.channel.basic_publish(
            exchange='',
            routing_key='metrics',
            body=json.dumps(metrics)
        )

    def unicast(self, target, message):
        if random.random() < self.loss_prob:
            return
            
        self.channel.basic_publish(
            exchange='',
            routing_key=f'node_{target}',
            body=json.dumps(message)
        )

    def multicast(self, group, message):
        self.channel.basic_publish(
            exchange='multicast',
            routing_key=group,
            body=json.dumps(message)
        )

    def broadcast(self, message):
        self.channel.basic_publish(
            exchange='broadcast',
            routing_key='',
            body=json.dumps(message)
        )

    def gossip(self, message):
        neighbors = random.sample(
            range(self.total_nodes), 
            min(self.gossip_k, self.total_nodes - 1)
        )
        
        for node in neighbors:
            if node != self.node_id and random.random() >= self.loss_prob:
                self.unicast(node, message)

    def handle_message(self, ch, method, properties, body):
        if self.broken:
            return
            
        try:
            message = json.loads(body)
            message_id = message['id']
            
            if message_id in self.received_messages:
                return
                
            self.received_messages.add(message_id)
            self.send_metrics(message_id, 'received')
            
            if self.algorithm == 'unicast':
                pass
                
            elif self.algorithm == 'multicast':
                self.multicast(message.get('group', 'default'), message)
                
            elif self.algorithm == 'broadcast':
                self.broadcast(message)
                
            elif self.algorithm == 'gossip':
                self.gossip(message)
                
        except Exception as e:
            print(f"Error processing message: {e}")

    def start(self):
        self.channel.basic_consume(
            queue=f'node_{self.node_id}',
            on_message_callback=self.handle_message,
            auto_ack=True
        )
        
        threading.Thread(target=self.channel.start_consuming, daemon=True).start()
        
        if self.node_id == 0:
            time.sleep(10)
            message = {
                'id': f'msg_{int(time.time())}',
                'origin': self.node_id,
                'created_at': datetime.utcnow().isoformat()
            }
            if self.algorithm == 'multicast':
                message['group'] = 'group_a'
            
            self.send_metrics(message['id'], 'initiated')
            
            if self.algorithm == 'unicast':
                for i in range(1, self.total_nodes):
                    self.unicast(i, message)
            elif self.algorithm == 'multicast':
                self.multicast(message['group'], message)
            elif self.algorithm == 'broadcast':
                self.broadcast(message)
            elif self.algorithm == 'gossip':
                self.gossip(message)

    def run(self):
        self.start()
        while True:
            time.sleep(1)

if __name__ == "__main__":
    node = DistributedNode()
    node.run()