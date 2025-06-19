import pika
import os
import json
import time
import random
import threading
import logging
import re
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(f"node_{os.getenv('NODE_ID', 'unknown')}")

class DistributedNode:
    def __init__(self):
        hostname = os.getenv('HOSTNAME', '')
        match = re.search(r'\d+$', hostname)
        
        if match:
            self.node_id = int(match.group())
        else:
            self.node_id = random.randint(0, 1000)
            print(f"⚠️ Не удалось определить ID из HOSTNAME, используем случайный: {self.node_id}")
        
        print(f"✅ Node ID установлен: {self.node_id}")
        
        self.total_nodes = int(os.getenv('TOTAL_NODES', 100))
        self.algorithm = os.getenv('ALGORITHM', 'gossip')
        self.loss_prob = float(os.getenv('LOSS_PROBABILITY', 0.0))
        self.gossip_k = int(os.getenv('GOSSIP_K', 3))
        self.broken = random.random() < float(os.getenv('BROKEN_PROBABILITY', 0.0))
        self.rabbitmq_host = os.getenv('RABBITMQ_HOST', 'rabbitmq')
        
        self.gossip_mode = os.getenv('GOSSIP_MODE', 'push')
        self.adaptive_gossip = os.getenv('ADAPTIVE_GOSSIP', 'false').lower() == 'true'
        self.priority_nodes = []
        
        self.received_messages = set()
        self.connection = None
        self.channel = None
        self.setup_rabbitmq()
        
        self.message_counter = 0
        self.last_activity = time.time()

    def setup_rabbitmq(self):
        credentials = pika.PlainCredentials('admin', 'admin')
        parameters = pika.ConnectionParameters(
            host=self.rabbitmq_host,
            port=5672,
            virtual_host='/',
            credentials=credentials,
            connection_attempts=10,
            retry_delay=3,
            socket_timeout=5
        )
        
        self.connection = pika.BlockingConnection(parameters)
        self.channel = self.connection.channel()
        
        self.channel.queue_declare(queue=f'node_{self.node_id}')
        
        self.channel.exchange_declare(exchange='broadcast', exchange_type='fanout')
        self.channel.exchange_declare(exchange='multicast', exchange_type='topic')
        
        self.channel.queue_bind(exchange='broadcast', queue=f'node_{self.node_id}')
        
        self.channel.queue_declare(queue='metrics')
        
        logger.info(f"Node {self.node_id} подключен к RabbitMQ")

    def send_metrics(self, message_id, action, **kwargs):
        metrics = {
            'node_id': self.node_id,
            'message_id': message_id,
            'action': action,
            'timestamp': datetime.utcnow().isoformat(),
            'algorithm': self.algorithm,
            'gossip_k': self.gossip_k,
            'gossip_mode': self.gossip_mode,
            'adaptive': self.adaptive_gossip,
            'loss_prob': self.loss_prob,
            'broken': self.broken
        }
        metrics.update(kwargs)
        
        self.channel.basic_publish(
            exchange='',
            routing_key='metrics',
            body=json.dumps(metrics)
        )

    def unicast(self, target, message):
        if random.random() < self.loss_prob:
            self.send_metrics(message['id'], 'packet_loss', target=target)
            return
            
        self.channel.basic_publish(
            exchange='',
            routing_key=f'node_{target}',
            body=json.dumps(message)
        )
        self.send_metrics(message['id'], 'sent', target=target)

    def multicast(self, group, message):
        self.channel.basic_publish(
            exchange='multicast',
            routing_key=group,
            body=json.dumps(message)
        )
        self.send_metrics(message['id'], 'multicast_sent', group=group)

    def broadcast(self, message):
        self.channel.basic_publish(
            exchange='broadcast',
            routing_key='',
            body=json.dumps(message)
        )
        self.send_metrics(message['id'], 'broadcast_sent')

    def gossip(self, message):
        if self.adaptive_gossip:
            current_k = self.gossip_k
            inactive_time = time.time() - self.last_activity
            if inactive_time > 5:
                current_k = min(self.gossip_k * 2, self.total_nodes // 2)
                logger.info(f"Node {self.node_id} увеличивает gossip_k до {current_k}")
        else:
            current_k = self.gossip_k
        
        if self.priority_nodes:
            neighbors = random.choices(
                self.priority_nodes,
                k=min(current_k, len(self.priority_nodes)))
        else:
            neighbors = random.sample(
                range(self.total_nodes), 
                min(current_k, self.total_nodes - 1)
            )
        
        if self.node_id in neighbors:
            neighbors.remove(self.node_id)
        
        if self.gossip_mode == 'push-pull':
            for node in neighbors:
                if random.random() >= self.loss_prob:
                    self.unicast(node, message)
            
            pull_message = {
                'id': f"pull_{message['id']}",
                'type': 'pull_request',
                'original_id': message['id']
            }
            for node in random.sample(neighbors, min(2, len(neighbors))):
                self.unicast(node, pull_message)
                
        elif self.gossip_mode == 'pull':
            pull_message = {
                'id': f"pull_{message['id']}",
                'type': 'pull_request',
                'original_id': message['id']
            }
            for node in neighbors:
                self.unicast(node, pull_message)
                
        else:
            for node in neighbors:
                if random.random() >= self.loss_prob:
                    self.unicast(node, message)

    def handle_message(self, ch, method, properties, body):
        if self.broken:
            self.send_metrics("system", "node_broken")
            return
            
        try:
            message = json.loads(body)
            self.last_activity = time.time()
            
            if message.get('type') == 'pull_request':
                original_id = message.get('original_id')
                if original_id in self.received_messages:
                    response = {
                        'id': f"response_{original_id}",
                        'type': 'pull_response',
                        'original_id': original_id,
                        'content': f"Response for {original_id}"
                    }
                    self.unicast(message['origin'], response)
                return
                
            message_id = message['id']
            
            if message_id in self.received_messages:
                return
                
            self.received_messages.add(message_id)
            self.send_metrics(message_id, 'received')
            self.message_counter += 1
            
            if self.message_counter > 10 and not self.priority_nodes:
                self.priority_nodes = random.sample(
                    range(self.total_nodes), 
                    min(10, self.total_nodes // 10))
                logger.info(f"Node {self.node_id} установил приоритетные узлы: {self.priority_nodes}")
            
            if self.algorithm == 'unicast':
                pass
                
            elif self.algorithm == 'multicast':
                self.multicast(message.get('group', 'default'), message)
                
            elif self.algorithm == 'broadcast':
                self.broadcast(message)
                
            elif self.algorithm == 'gossip':
                self.gossip(message)
                
        except Exception as e:
            logger.error(f"Error processing message: {e}")

    def start(self):
        self.channel.basic_consume(
            queue=f'node_{self.node_id}',
            on_message_callback=self.handle_message,
            auto_ack=True
        )
        
        threading.Thread(target=self.channel.start_consuming, daemon=True).start()
        
        if self.should_initiate():
            time.sleep(10)
            self.initiate_message()

    def should_initiate(self):
        return random.random() < (1.0 / self.total_nodes)

    def initiate_message(self):
        message = {
            'id': f'msg_{int(time.time())}_{self.node_id}',
            'origin': self.node_id,
            'created_at': datetime.utcnow().isoformat(),
            'group': 'group_a' if self.algorithm == 'multicast' else None
        }
        
        self.send_metrics(message['id'], 'initiated')
        
        if self.algorithm == 'unicast':
            for i in range(self.total_nodes):
                if i != self.node_id:
                    self.unicast(i, message)
        elif self.algorithm == 'multicast':
            self.multicast(message['group'], message)
        elif self.algorithm == 'broadcast':
            self.broadcast(message)
        elif self.algorithm == 'gossip':
            self.gossip(message)
        
        logger.info(f"Node {self.node_id} инициировал сообщение: {message['id']}")

    def run(self):
        self.start()
        while True:
            time.sleep(1)

if __name__ == "__main__":
    node = DistributedNode()
    node.run()