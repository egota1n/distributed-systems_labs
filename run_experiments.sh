#!/bin/bash

ALGORITHMS=("unicast" "multicast" "broadcast" "gossip")
GOSSIP_MODES=("push" "pull" "push-pull")
LOSS_PROBABILITIES=(0.0 0.01 0.05 0.1)
BROKEN_PROBABILITIES=(0.0 0.05 0.1)
GOSSIP_K_VALUES=(3 5 7)
ADAPTIVE_OPTIONS=("true" "false")
TOTAL_NODES=100

docker-compose down -v
rm -rf results/*
mkdir -p results

run_experiment() {
    ALGO=$1
    LOSS=$2
    BROKEN=$3
    K=$4
    MODE=$5
    ADAPTIVE=$6
    
    echo "Запуск эксперимента: $ALGO, loss=$LOSS, broken=$BROKEN, k=$K, mode=$MODE, adaptive=$ADAPTIVE"
    
    cat > .env <<EOL
TOTAL_NODES=$TOTAL_NODES
ALGORITHM=$ALGO
LOSS_PROBABILITY=$LOSS
BROKEN_PROBABILITY=$BROKEN
GOSSIP_K=$K
GOSSIP_MODE=$MODE
ADAPTIVE_GOSSIP=$ADAPTIVE
EOL

    docker-compose up --scale node=$TOTAL_NODES --abort-on-container-exit
}

for algo in "${ALGORITHMS[@]}"; do
    for loss in "${LOSS_PROBABILITIES[@]}"; do
        for broken in "${BROKEN_PROBABILITIES[@]}"; do
            
            if [ "$algo" == "gossip" ]; then
                for mode in "${GOSSIP_MODES[@]}"; do
                    for k in "${GOSSIP_K_VALUES[@]}"; do
                        for adaptive in "${ADAPTIVE_OPTIONS[@]}"; do
                            run_experiment "$algo" "$loss" "$broken" "$k" "$mode" "$adaptive"
                        done
                    done
                done
            else
                run_experiment "$algo" "$loss" "$broken" 3 "push" "false"
            fi
            
        done
    done
done

echo "Все эксперименты завершены"