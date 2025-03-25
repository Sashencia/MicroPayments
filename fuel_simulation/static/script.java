document.getElementById('fuel-button').addEventListener('click', function() {
    const button = this;
    fetch('/toggle_fueling', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'started') {
            button.textContent = 'Stop Fueling';
            button.style.backgroundColor = '#dc3545';
            document.getElementById('status').textContent = 'Fueling in progress...';
            startUpdatingFuelData();
        } else {
            button.textContent = 'Start Fueling';
            button.style.backgroundColor = '#28a745';
            document.getElementById('status').textContent = 'Fueling stopped.';
            stopUpdatingFuelData();
            updateFuelData(); // Final update
        }
    })
    .catch(error => console.error("Error:", error));
});

let updateInterval;

function updateFuelData() {
    fetch('/get_fuel_data')
        .then(response => response.json())
        .then(data => {
            console.log("Received data:", data); // Отладка
            
            // Обновляем цифровые значения
            document.getElementById('total-liters').textContent = data.total_liters.toFixed(3);
            document.getElementById('total-cost').textContent = data.total_cost.toFixed(2);
            document.getElementById('balance').textContent = data.balance.toFixed(2);
            document.getElementById('recipient-balance').textContent = data.recipient_balance.toFixed(2);
            document.getElementById('real-time-liters').textContent = data.real_time_data.liters.toFixed(3);
            document.getElementById('real-time-balance').textContent = data.real_time_data.balance.toFixed(2);
            
            // Обновляем таблицы
            updateTable('packet-log', data.packet_log || []);
            updateTable('opkcmp-log', data.opkcmp_log || []);
        })
        .catch(error => console.error("Error:", error));
}

function updateTable(tableId, data) {
    const table = document.getElementById(tableId);
    if (!table) {
        console.error(`Table ${tableId} not found`);
        return;
    }
    
    const tbody = table.querySelector('tbody');
    if (!tbody) {
        console.error(`tbody not found in table ${tableId}`);
        return;
    }
    
    // Очищаем и заполняем таблицу
    tbody.innerHTML = data.map(item => `
        <tr style="${item.is_final ? 'background-color: #ffcccc;' : ''}">
            <td>${item.time || '00:00:00.000'}</td>
            <td>${(item.liters || 0).toFixed(3)}</td>
            <td>${(item.balance || 0).toFixed(2)}</td>
            <td>${item.is_final ? 'FINISHED' : 'In Progress'}</td>
        </tr>
    `).join('');
    
    // Если данных нет
    if (data.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4">No data available</td></tr>';
    }
}

function startUpdatingFuelData() {
    updateFuelData(); // Сразу обновляем
    updateInterval = setInterval(updateFuelData, 300); // Обновляем каждые 300мс
}

function stopUpdatingFuelData() {
    clearInterval(updateInterval);
}