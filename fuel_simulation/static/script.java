document.addEventListener('DOMContentLoaded', function() {
    const fuelBtn = document.getElementById('fuel-button');
    const statusEl = document.getElementById('status');
    let isFueling = false;
    let updateInterval;
    
    // Обработчик кнопки заправки
    fuelBtn.addEventListener('click', function() {
        if (isFueling) {
            stopFueling();
        } else {
            startFueling();
        }
    });

    function startFueling() {
        fetch('/toggle_fueling', { method: 'POST' })
            .then(response => response.json())
            .then(data => {
                if (data.status === 'started') {
                    isFueling = true;
                    fuelBtn.textContent = 'Stop Fueling';
                    fuelBtn.classList.add('stop');
                    statusEl.textContent = 'Fueling in progress...';
                    
                    // Запускаем обновление данных с более частым интервалом
                    updateFuelData();
                    updateInterval = setInterval(updateFuelData, 100); // 100ms для плавности
                }
            });
    }

    function stopFueling() {
        fetch('/toggle_fueling', { method: 'POST' })
            .then(response => response.json())
            .then(data => {
                if (data.status === 'stopped') {
                    isFueling = false;
                    fuelBtn.textContent = 'Start Fueling';
                    fuelBtn.classList.remove('stop');
                    statusEl.textContent = 'Fueling stopped';
                    clearInterval(updateInterval);
                }
            });
    }

    function updateFuelData() {
        fetch('/get_fuel_data')
            .then(response => response.json())
            .then(data => {
                // Обновляем цифровые значения
                updateRealTimeValues(data);
                
                // Обновляем таблицы с пояснениями
                updateHoldTable(data);
                updatePacketTable(data);
                updateOPKCMPTable(data);
                
                // Обновляем визуализацию потока с реальными значениями
                updateFlowVisualization(data);
                
                // Добавляем анимацию процесса
                animateFuelingProcess(data);
            });
    }
    
    function animateFuelingProcess(data) {
        const fuelingIndicator = document.getElementById('fueling-animation');
        if (data.fueling_active && fuelingIndicator) {
            fuelingIndicator.style.animationPlayState = 'running';
        } else if (fuelingIndicator) {
            fuelingIndicator.style.animationPlayState = 'paused';
        }
    }
    
    function updateFlowVisualization(data) {
        // Рассчитываем текущую скорость потока (литры в секунду)
        const flowRate = data.real_time_data.liters / (data.packet_log.length * 0.1); // примерный расчет
        const flowPercentage = Math.min(100, (flowRate / 6) * 100); // 6 л/с - максимальная скорость
        
        document.getElementById('flow-indicator').style.width = `${flowPercentage}%`;
        document.getElementById('current-flow').textContent = `${flowRate.toFixed(3)} L/s`;
        
        // Рассчитываем текущую скорость оплаты (рубли в секунду)
        const paymentRate = (data.total_cost / (data.packet_log.length * 0.1)) || 0;
        const paymentPercentage = Math.min(100, (paymentRate / 326.22) * 100); // 54.37 * 6 = 326.22
        
        document.getElementById('payment-indicator').style.width = `${paymentPercentage}%`;
        document.getElementById('current-payment').textContent = `${paymentRate.toFixed(2)} RUB/s`;
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

    function updateHoldTable(data) {
        const table = document.getElementById('holds-log');
        const tbody = table.querySelector('tbody');
        tbody.innerHTML = '';
        
        // Добавляем текущий холд (если есть)
        if (data.current_hold) {
            const row = document.createElement('tr');
            row.className = 'current-hold';
            row.innerHTML = `
                <td>${new Date().toLocaleTimeString()}</td>
                <td>${data.current_hold.amount.toFixed(2)} RUB</td>
                <td>${data.current_hold.remaining.toFixed(2)} RUB</td>
                <td>${data.current_hold.status.toUpperCase()}</td>
            `;
            tbody.appendChild(row);
        }
        
        // Добавляем историю холдов (5 последних)
        const holdsToShow = (data.holds || []).slice(-5).reverse();
        
        holdsToShow.forEach(hold => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>${new Date(hold.timestamp).toLocaleTimeString()}</td>
                <td>${hold.amount.toFixed(2)} RUB</td>
                <td>${hold.remaining.toFixed(2)} RUB</td>
                <td>${hold.status.toUpperCase()}</td>
            `;
            tbody.appendChild(row);
        });
        
        if (tbody.children.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4">No active holds</td></tr>';
        }
    }

    function updatePacketTable(data) {
        const table = document.getElementById('packet-log');
        const tbody = table.querySelector('tbody');
        tbody.innerHTML = '';
        
        // Показываем только последние 10 пакетов для производительности
        const packetsToShow = data.packet_log.slice(-10).reverse();
        
        packetsToShow.forEach(packet => {
            // Основная строка пакета
            const packetRow = document.createElement('tr');
            packetRow.className = packet.is_final ? 'final-packet' : 'packet';
            packetRow.innerHTML = `
                <td>${packet.time || new Date().toLocaleTimeString()}</td>
                <td>${packet.liters.toFixed(3)} L</td>
                <td>${packet.balance.toFixed(2)} RUB</td>
                <td>${packet.is_final ? 'FINAL' : 'PACKET'}</td>
            `;
            tbody.appendChild(packetRow);
            
            // Подробные кадры (если есть)
            if (packet.frames && packet.frames.length > 0) {
                packet.frames.forEach(frame => {
                    const frameRow = document.createElement('tr');
                    frameRow.className = 'frame-detail';
                    frameRow.innerHTML = `
                        <td class="frame-time">↳ ${frame.time || '--:--:--'}</td>
                        <td>${frame.liters.toFixed(3)} L</td>
                        <td>${frame.balance.toFixed(2)} RUB</td>
                        <td>FRAME</td>
                    `;
                    tbody.appendChild(frameRow);
                });
            }
        });
        
        if (tbody.children.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4">No packets data</td></tr>';
        }
    }

    function updateOPKCMPTable(data) {
        const table = document.getElementById('opkcmp-log');
        const tbody = table.querySelector('tbody');
        tbody.innerHTML = '';
        
        // Показываем только последние 10 записей
        const opkcmpToShow = data.opkcmp_log.slice(-10).reverse();
        
        opkcmpToShow.forEach(item => {
            const row = document.createElement('tr');
            row.className = item.is_final ? 'final-opkcmp' : 'opkcmp';
            row.innerHTML = `
                <td>${item.time || new Date().toLocaleTimeString()}</td>
                <td>${item.liters.toFixed(3)} L</td>
                <td>${item.balance.toFixed(2)} RUB</td>
                <td>${item.is_final ? 'FINAL' : 'BUFFER'}</td>
            `;
            tbody.appendChild(row);
        });
        
        if (tbody.children.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4">No OPKCMP data</td></tr>';
        }
    }

    function updateRealTimeChart(data) {
        // Здесь можно добавить код для обновления графика в реальном времени
        // Например, с использованием Chart.js или аналогичной библиотеки
    }
});