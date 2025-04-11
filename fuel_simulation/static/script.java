document.addEventListener('DOMContentLoaded', function() {
    const fuelBtn = document.getElementById('fuel-button');
    const statusEl = document.getElementById('status');
    let isFueling = false;
    let updateInterval;

    // Инициализация UI
    updateFuelData();
    
    fuelBtn.addEventListener('click', toggleFueling);

    async function toggleFueling() {
        try {
            const response = await fetch('/toggle_fueling', { 
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            });
            const data = await response.json();
            
            if (data.status === 'started') {
                isFueling = true;
                fuelBtn.textContent = 'Stop Fueling';
                fuelBtn.classList.add('stop');
                statusEl.textContent = 'Fueling in progress...';
                statusEl.dataset.status = 'active';
                updateInterval = setInterval(updateFuelData, 100);
            } else if (data.status === 'stopped') {
                isFueling = false;
                fuelBtn.textContent = 'Start Fueling';
                fuelBtn.classList.remove('stop');
                statusEl.textContent = 'Ready to start fueling';
                statusEl.dataset.status = 'inactive';
                clearInterval(updateInterval);
                updateFuelData();
            }
        } catch (error) {
            console.error('Error toggling fueling:', error);
            alert('Failed to toggle fueling state');
        }
    }

    function updateFuelData() {
        fetch('/get_fuel_data')
            .then(response => response.json())
            .then(data => {
                updateRealTimeValues(data);
                updateHoldTable(data.holds);
                updatePacketTable(data.packet_log);
                updateOPKCMPTable(data.opkcmp_log);
                updateFlowVisualization(data);
                animateFuelingProcess(data);
            })
            .catch(error => console.error('Error updating fuel data:', error));
    }

    function updateRealTimeValues(data) {
        document.getElementById('real-time-liters').textContent = 
            data.real_time_data.liters.toFixed(3) + ' L';
        document.getElementById('real-time-balance').textContent = 
            data.real_time_data.balance.toFixed(2) + ' RUB';
        document.getElementById('total-liters').textContent = 
            data.total_liters.toFixed(3) + ' L';
        document.getElementById('total-cost').textContent = 
            data.total_cost.toFixed(2) + ' RUB';
        document.getElementById('balance').textContent = 
            data.balance.toFixed(2) + ' RUB';
        document.getElementById('recipient-balance').textContent = 
            data.recipient_balance.toFixed(2) + ' RUB';
    }

    function updateHoldTable(holds) {
        const tbody = document.querySelector('#holds-log tbody');
        tbody.innerHTML = '';
        
        holds.forEach(hold => {
            const row = document.createElement('tr');
            
            // Определяем класс строки в зависимости от состояния холда
            let rowClass = '';
            if (hold.status === 'completed') {
                rowClass = 'hold-completed';
            } else if (hold.used / hold.amount > 0.66) {
                rowClass = 'hold-used-2-3';
            } else {
                rowClass = 'hold-active';
            }
            
            row.className = rowClass;
            row.innerHTML = `
                <td>${hold.id}</td>
                <td>${hold.timestamp}</td>
                <td>${hold.amount.toFixed(2)} RUB</td>
                <td>${hold.used.toFixed(2)} RUB</td>
                <td>${hold.remaining.toFixed(2)} RUB</td>
                <td>${hold.status.toUpperCase()}</td>
                <td>${hold.transactions.length}</td>
            `;
            tbody.appendChild(row);
        });
    }

    function updatePacketTable(packets) {
        const tbody = document.querySelector('#packet-log tbody');
        tbody.innerHTML = '';
        
        packets.forEach(packet => {
            const row = document.createElement('tr');
            row.className = packet.is_final ? 'final-frame' : 'packet-frame';
            row.innerHTML = `
                <td>${packet.time}</td>
                <td>${packet.liters.toFixed(3)} L</td>
                <td>${packet.balance.toFixed(2)} RUB</td>
                <td>${packet.is_final ? 'FINAL' : 'PACKET'}</td>
            `;
            tbody.appendChild(row);
        });
    }

    function updateOPKCMPTable(opkcmpLog) {
        const tbody = document.querySelector('#opkcmp-log tbody');
        tbody.innerHTML = '';
        
        opkcmpLog.forEach(item => {
            const row = document.createElement('tr');
            row.className = item.is_final ? 'final-opkcmp' : 'opkcmp-buffer';
            row.innerHTML = `
                <td>${item.time}</td>
                <td>${item.liters.toFixed(3)} L</td>
                <td>${item.balance.toFixed(2)} RUB</td>
                <td>${item.is_final ? 'FINAL' : 'BUFFER'}</td>
            `;
            tbody.appendChild(row);
        });
    }

    function updateFlowVisualization(data) {
        // Расчет скорости потока топлива
        const flowRate = data.real_time_data.liters / (data.packet_log.length * 0.1) || 0;
        const flowPercentage = Math.min(100, (flowRate / 6) * 100);
        
        document.getElementById('flow-indicator').style.width = `${flowPercentage}%`;
        document.getElementById('current-flow').textContent = `${flowRate.toFixed(3)} L/s`;
        
        // Расчет скорости оплаты
        const paymentRate = (data.total_cost / (data.packet_log.length * 0.1)) || 0;
        const paymentPercentage = Math.min(100, (paymentRate / 326.22) * 100);
        
        document.getElementById('payment-indicator').style.width = `${paymentPercentage}%`;
        document.getElementById('current-payment').textContent = `${paymentRate.toFixed(2)} RUB/s`;
    }

    function animateFuelingProcess(data) {
        const animation = document.getElementById('fueling-animation');
        if (data.fueling_active) {
            animation.style.animationPlayState = 'running';
        } else {
            animation.style.animationPlayState = 'paused';
        }
    }
});